export const COMPOSER_TEXTAREA_MIN_HEIGHT = 48;
export const COMPOSER_TEXTAREA_MAX_HEIGHT = 144;

export function getAutosizeTextareaHeight(
  scrollHeight: number,
  minHeight = COMPOSER_TEXTAREA_MIN_HEIGHT,
  maxHeight = COMPOSER_TEXTAREA_MAX_HEIGHT
) {
  return `${Math.min(Math.max(scrollHeight, minHeight), maxHeight)}px`;
}
