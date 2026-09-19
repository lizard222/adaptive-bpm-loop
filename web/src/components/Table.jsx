// Общий каркас таблицы — заменяет thead/tbody-вёрстку, продублированную в
// Processes.jsx (ControlPointsTable) и TaskList.jsx. renderRow(row)
// возвращает содержимое строки (<td>...</td> подряд), сам <tr> — здесь.
export default function Table({ columns, rows, rowKey, renderRow }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gridline text-left text-xs uppercase tracking-wide text-ink-muted dark:border-white/10">
            {columns.map((col) => (
              <th key={col} className="py-2 pr-3 font-medium">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} className="border-b border-gridline last:border-0 dark:border-white/10">
              {renderRow(row)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
