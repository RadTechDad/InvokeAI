import torch
from diffusers.image_processor import VaeImageProcessor
from diffusers.models.attention_processor import (
    AttnProcessor2_0,
    LoRAAttnProcessor2_0,
    LoRAXFormersAttnProcessor,
    XFormersAttnProcessor,
)
from diffusers.models.autoencoders.autoencoder_kl import AutoencoderKL
from diffusers.models.autoencoders.autoencoder_tiny import AutoencoderTiny
from PIL import Image

from invokeai.app.invocations.baseinvocation import BaseInvocation, invocation
from invokeai.app.invocations.constants import DEFAULT_PRECISION
from invokeai.app.invocations.fields import (
    FieldDescriptions,
    Input,
    InputField,
    LatentsField,
    WithBoard,
    WithMetadata,
)
from invokeai.app.invocations.model import VAEField
from invokeai.app.invocations.primitives import ImageOutput
from invokeai.app.services.shared.invocation_context import InvocationContext
from invokeai.backend.model_manager.load.load_base import LoadedModel
from invokeai.backend.stable_diffusion import set_seamless
from invokeai.backend.util.devices import TorchDevice


@invocation(
    "l2i",
    title="Latents to Image",
    tags=["latents", "image", "vae", "l2i"],
    category="latents",
    version="1.2.2",
)
class LatentsToImageInvocation(BaseInvocation, WithMetadata, WithBoard):
    """Generates an image from latents."""

    latents: LatentsField = InputField(
        description=FieldDescriptions.latents,
        input=Input.Connection,
    )
    vae: VAEField = InputField(
        description=FieldDescriptions.vae,
        input=Input.Connection,
    )
    tiled: bool = InputField(default=False, description=FieldDescriptions.tiled)
    fp32: bool = InputField(default=DEFAULT_PRECISION == torch.float32, description=FieldDescriptions.fp32)

    @staticmethod
    def vae_decode(
        context: InvocationContext,
        vae_info: LoadedModel,
        seamless_axes: list[str],
        latents: torch.Tensor,
        use_fp32: bool,
        use_tiling: bool,
    ) -> Image.Image:
        assert isinstance(vae_info.model, (AutoencoderKL, AutoencoderTiny))
        with set_seamless(vae_info.model, seamless_axes), vae_info as vae:
            assert isinstance(vae, (AutoencoderKL, AutoencoderTiny))
            latents = latents.to(vae.device)
            if use_fp32:
                vae.to(dtype=torch.float32)

                use_torch_2_0_or_xformers = hasattr(vae.decoder, "mid_block") and isinstance(
                    vae.decoder.mid_block.attentions[0].processor,
                    (
                        AttnProcessor2_0,
                        XFormersAttnProcessor,
                        LoRAXFormersAttnProcessor,
                        LoRAAttnProcessor2_0,
                    ),
                )
                # if xformers or torch_2_0 is used attention block does not need
                # to be in float32 which can save lots of memory
                if use_torch_2_0_or_xformers:
                    vae.post_quant_conv.to(latents.dtype)
                    vae.decoder.conv_in.to(latents.dtype)
                    vae.decoder.mid_block.to(latents.dtype)
                else:
                    latents = latents.float()

            else:
                vae.to(dtype=torch.float16)
                latents = latents.half()

            if use_tiling or context.config.get().force_tiled_decode:
                vae.enable_tiling()
            else:
                vae.disable_tiling()

            # clear memory as vae decode can request a lot
            TorchDevice.empty_cache()

            with torch.inference_mode():
                # copied from diffusers pipeline
                latents = latents / vae.config.scaling_factor
                image = vae.decode(latents, return_dict=False)[0]
                image = (image / 2 + 0.5).clamp(0, 1)  # denormalize
                # we always cast to float32 as this does not cause significant overhead and is compatible with bfloat16
                np_image = image.cpu().permute(0, 2, 3, 1).float().numpy()

                image = VaeImageProcessor.numpy_to_pil(np_image)[0]

        TorchDevice.empty_cache()

        return image

    @torch.no_grad()
    def invoke(self, context: InvocationContext) -> ImageOutput:
        latents = context.tensors.load(self.latents.latents_name)
        vae_info = context.models.load(self.vae.vae)

        image = self.vae_decode(
            context=context,
            vae_info=vae_info,
            seamless_axes=self.vae.seamless_axes,
            latents=latents,
            use_fp32=self.fp32,
            use_tiling=self.tiled,
        )
        image_dto = context.images.save(image=image)

        return ImageOutput.build(image_dto)