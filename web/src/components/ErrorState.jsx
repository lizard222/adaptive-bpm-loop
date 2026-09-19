import Button from "./Button.jsx";

// До редизайна ошибка загрузки была статичным красным текстом без способа
// восстановиться, кроме ручной кнопки "Обновить" на самом экране — а в
// Documents.jsx начальная загрузка вообще не имела обработки ошибок.
// onRetry — необязателен: там, где повторный запрос не имеет смысла (или
// уже есть своя кнопка обновления), можно не передавать.
export default function ErrorState({ message, onRetry }) {
  return (
    <div className="flex flex-col items-center gap-3 py-6 text-center">
      <p className="text-sm text-status-critical">{message}</p>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>
          Повторить
        </Button>
      )}
    </div>
  );
}
