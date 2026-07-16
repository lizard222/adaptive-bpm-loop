import { useEffect, useState } from "react";
import * as api from "./api.js";

const KIND_LABELS = {
  shift_start: "Сдвиг срока запуска",
  review_duration: "Пересмотр норматива длительности",
  add_checkpoint: "Добавление контрольной точки",
};

export default function CorrectionsPanel() {
  const [items, setItems] = useState([]);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);

  async function refresh() {
    try {
      const data = await api.listPendingCorrections();
      setItems(data.pending);
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function decide(item, decision) {
    setBusyId(item.id);
    try {
      await api.decideCorrection(item.id, decision);
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Корректировки контура адаптации</h2>
        <button className="ghost" onClick={refresh}>
          Обновить
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {items.length === 0 ? (
        <p className="empty">Нет предложений, ожидающих решения.</p>
      ) : (
        <ul className="corrections">
          {items.map((c) => (
            <li key={c.id}>
              <div className="correction-head">
                <span className="badge">{KIND_LABELS[c.kind] || c.kind}</span>
                <span className="mono">
                  {c.process_key} · шаг «{c.target}»
                </span>
              </div>
              <p className="justification">{c.justification}</p>
              <div className="correction-actions">
                <button disabled={busyId === c.id} onClick={() => decide(c, "accept")}>
                  Принять
                </button>
                <button className="danger" disabled={busyId === c.id} onClick={() => decide(c, "reject")}>
                  Отклонить
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
