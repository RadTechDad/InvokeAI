import { IconButton } from '@invoke-ai/ui-library';
import { useSelectTool, useToolIsSelected } from 'features/controlLayers/components/Tool/hooks';
import { useRegisteredHotkeys } from 'features/system/components/HotkeysModal/useHotkeyData';
import { memo } from 'react';
import { useTranslation } from 'react-i18next';
import { PiEraserBold } from 'react-icons/pi';

export const ToolEraserButton = memo(() => {
  const { t } = useTranslation();
  const isSelected = useToolIsSelected('eraser');
  const selectEraser = useSelectTool('eraser');

  useRegisteredHotkeys({
    id: 'selectEraserTool',
    category: 'canvas',
    callback: selectEraser,
    options: { enabled: !isSelected },
    dependencies: [isSelected, selectEraser],
  });

  return (
    <IconButton
      aria-label={`${t('controlLayers.tool.eraser')} (E)`}
      tooltip={`${t('controlLayers.tool.eraser')} (E)`}
      icon={<PiEraserBold />}
      colorScheme={isSelected ? 'invokeBlue' : 'base'}
      variant="solid"
      onClick={selectEraser}
      isDisabled={isSelected}
    />
  );
});

ToolEraserButton.displayName = 'ToolEraserButton';
