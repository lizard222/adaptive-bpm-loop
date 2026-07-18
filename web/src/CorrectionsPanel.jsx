import { useEffect, useState } from "react";
import * as api from "./api.js";
import Badge from "./Badge.jsx";
import { KIND_LABELS } from "./constants.js";

export default function CorrectionsPanel() {
  const [items, setItems] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);

  async function refresh() {
    try {
      const data = await api.listPendingCorrections();
      setItems(data.pending);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
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
    <section className="rounded-lg border border-gridline bg-surface p-5 dark:border-white/10 dark:bg-surface-dark">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-semibold text-ink dark:text-ink-dark">Корректировки контура адаптации</h2>
        <button
          onClick={refresh}
          className="rounded-md border border-gridline px-3 py-1.5 text-xs font-medium text-ink-secondary hover:bg-page dark:border-white/10 dark:text-ink-dark-secondary dark:hover:bg-white/5"
        >
          Обновить
        </button>
      </div>
      {error && <p className="mb-4 text-sm text-status-critical">{error}</p>}
      {loading ? (
        <p className="py-6 text-center text-sm text-ink-muted">Загрузка…</p>
      ) : items.length === 0 ? (
        <p className="py-6 text-center text-sm text-ink-muted">Нет предложений, ожидающих решения.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((c) => (
            <li key={c.id} className="rounded-md border border-gridline p-4 dark:border-white/10">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <Badge tone="accent">{KIND_LABELS[c.kind] || c.kind}</Badge>
                <span className="font-mono text-xs text-ink-muted">
                  {c.process_key} · шаг «{c.target}»
                </span>
              </div>
              <p className="mb-3 text-sm text-ink-secondary dark:text-ink-dark-secondary">{c.justification}</p>
              <div className="flex gap-2">
                <button
                  disabled={busyId === c.id}
                  onClick={() => decide(c, "accept")}
                  className="rounded-md bg-status-good px-3 py-1.5 text-xs font-medium text-white hover:brightness-110 disabled:opacity-60"
                >
                  Принять
                </button>
                <button
                  disabled={busyId === c.id}
                  onClick={() => decide(c, "reject")}
                  className="rounded-md bg-status-critical px-3 py-1.5 text-xs font-medium text-white hover:brightness-110 disabled:opacity-60"
                >
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
