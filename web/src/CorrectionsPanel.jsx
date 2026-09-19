import { useState } from "react";
import * as api from "./api.js";
import Badge from "./components/Badge.jsx";
import Card from "./components/Card.jsx";
import Button from "./components/Button.jsx";
import LoadingState from "./components/LoadingState.jsx";
import ErrorState from "./components/ErrorState.jsx";
import EmptyState from "./components/EmptyState.jsx";
import ConfirmDialog from "./components/ConfirmDialog.jsx";
import { useApiData } from "./useApiData.js";
import { useToast } from "./components/Toast.jsx";
import { KIND_LABELS } from "./constants.js";

export default function CorrectionsPanel() {
  const { data, error, loading, refresh } = useApiData(api.listPendingCorrections);
  const [confirm, setConfirm] = useState(null); // { item, decision }
  const [busy, setBusy] = useState(false);
  const showToast = useToast();

  const items = data?.pending || [];

  async function decide() {
    if (!confirm) return;
    setBusy(true);
    try {
      await api.decideCorrection(confirm.item.id, confirm.decision);
      showToast(confirm.decision === "accept" ? "Корректировка принята" : "Корректировка отклонена");
      setConfirm(null);
      await refresh();
    } catch (e) {
      showToast(e.message, "critical");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Корректировки контура адаптации"
      actions={
        <Button variant="secondary" onClick={refresh}>
          Обновить
        </Button>
      }
    >
      {error ? (
        <ErrorState message={error} onRetry={refresh} />
      ) : loading ? (
        <LoadingState rows={3} />
      ) : items.length === 0 ? (
        <EmptyState message="Нет предложений, ожидающих решения." />
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
                <Button variant="success" onClick={() => setConfirm({ item: c, decision: "accept" })}>
                  Принять
                </Button>
                <Button variant="danger" onClick={() => setConfirm({ item: c, decision: "reject" })}>
                  Отклонить
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={!!confirm}
        title={confirm?.decision === "accept" ? "Принять корректировку?" : "Отклонить корректировку?"}
        body={
          confirm &&
          `${KIND_LABELS[confirm.item.kind] || confirm.item.kind} · шаг «${confirm.item.target}». Действие необратимо.`
        }
        confirmLabel={confirm?.decision === "accept" ? "Принять" : "Отклонить"}
        confirmVariant={confirm?.decision === "accept" ? "success" : "danger"}
        busy={busy}
        onConfirm={decide}
        onCancel={() => setConfirm(null)}
      />
    </Card>
  );
}
