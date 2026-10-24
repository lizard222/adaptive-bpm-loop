import { useState } from "react";
import * as api from "./api.js";
import Badge from "./components/Badge.jsx";
import Button from "./components/Button.jsx";
import Card from "./components/Card.jsx";
import ConfirmDialog from "./components/ConfirmDialog.jsx";
import EmptyState from "./components/EmptyState.jsx";
import ErrorState from "./components/ErrorState.jsx";
import FormField, { Select } from "./components/FormField.jsx";
import LoadingState from "./components/LoadingState.jsx";
import StatusDot from "./components/StatusDot.jsx";
import { useToast } from "./components/Toast.jsx";
import { useApiData } from "./useApiData.js";
import { fmtDate } from "./format.js";
import { relativeTime } from "./time.js";

const URGENCY_LABEL = { good: "В срок", warning: "Скоро срок", critical: "Срок истёк" };

// Статус этапа кодируется и формой маркера, и подписью — не только цветом.
const STAGE_MARK = {
  done: { symbol: "✓", label: "пройден", ring: "border-status-good bg-status-good text-white" },
  current: { symbol: "●", label: "вы здесь", ring: "border-accent bg-accent/10 text-accent dark:text-accent-dark" },
  upcoming: { symbol: "", label: "впереди", ring: "border-gridline text-ink-muted dark:border-white/20" },
  skipped: { symbol: "✕", label: "не пройден", ring: "border-status-critical text-status-critical" },
};

export default function MyDefense() {
  const { data, error, loading, refresh } = useApiData(api.getMyDefense);
  const [selectedCase, setSelectedCase] = useState(null);
  const [confirmStep, setConfirmStep] = useState(null);
  const [busy, setBusy] = useState(false);
  const showToast = useToast();

  if (loading) {
    return (
      <Card title="Моя защита">
        <LoadingState rows={5} />
      </Card>
    );
  }
  if (error) {
    return (
      <Card title="Моя защита">
        <ErrorState message={error} onRetry={refresh} />
      </Card>
    );
  }

  const defenses = data?.defenses || [];
  if (defenses.length === 0) {
    return (
      <Card title="Моя защита">
        <EmptyState message="Процесс защиты для вас ещё не запущен. Когда кафедра его запустит, здесь появятся этапы, сроки и список документов." />
      </Card>
    );
  }

  const defense = defenses.find((d) => d.case_id === selectedCase) || defenses[0];
  const current = defense.stages.find((s) => s.status === "current");

  async function complete() {
    setBusy(true);
    try {
      await api.completeTask(defense.case_id, confirmStep.step);
      showToast(`Этап «${confirmStep.title}» отмечен выполненным`);
      setConfirmStep(null);
      await refresh();
    } catch (e) {
      showToast(e.message, "critical");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {defenses.length > 1 && (
        <Card>
          <FormField label="Процесс защиты">
            <Select value={defense.case_id} onChange={(e) => setSelectedCase(e.target.value)} className="sm:w-96">
              {defenses.map((d) => (
                <option key={d.case_id} value={d.case_id}>
                  {d.case_id} — {d.status === "active" ? "идёт" : "завершён"}
                  {d.kind === "test" ? " (тест)" : ""}
                </option>
              ))}
            </Select>
          </FormField>
        </Card>
      )}

      <Card
        title={defense.status === "active" ? "Сейчас" : "Процесс защиты завершён"}
        actions={
          <Button variant="secondary" onClick={refresh}>
            Обновить
          </Button>
        }
      >
        {current ? (
          <CurrentStage stage={current} onComplete={() => setConfirmStep(current)} />
        ) : (
          <p className="text-sm text-ink-secondary dark:text-ink-dark-secondary">
            {defense.status === "active"
              ? "Сейчас нет открытого этапа."
              : "Все этапы процесса закрыты. История — в уведомлениях ниже."}
          </p>
        )}
      </Card>

      <Card title="Этапы защиты">
        <ol className="flex flex-col">
          {defense.stages.map((s, i) => (
            <StageRow key={s.step} stage={s} last={i === defense.stages.length - 1} />
          ))}
        </ol>
      </Card>

      <Card title="Уведомления">
        {defense.feed.length === 0 ? (
          <EmptyState message="Пока уведомлений нет." />
        ) : (
          <ul className="flex flex-col">
            {defense.feed.map((f, i) => (
              <li
                key={i}
                className="flex items-start gap-3 border-b border-gridline py-2 text-sm last:border-0 dark:border-white/10"
              >
                <span className="mt-1.5">
                  <StatusDot tone={f.tone} />
                </span>
                <span className="text-ink dark:text-ink-dark">{f.text}</span>
                <span className="ml-auto whitespace-nowrap text-xs text-ink-muted" title={fmtDate(f.ts)}>
                  {relativeTime(f.ts)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <ConfirmDialog
        open={!!confirmStep}
        title="Отметить этап выполненным?"
        body={confirmStep && `«${confirmStep.title}». Отметку нельзя отменить — кафедра увидит, что этап пройден.`}
        confirmLabel="Отметить"
        busy={busy}
        onConfirm={complete}
        onCancel={() => setConfirmStep(null)}
      />
    </>
  );
}

function CurrentStage({ stage, onComplete }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-lg font-semibold text-ink dark:text-ink-dark">{stage.title}</h3>
        {stage.is_mine ? <Badge tone="accent">ваш шаг</Badge> : <Badge tone="neutral">выполняет: {stage.actor}</Badge>}
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-ink-muted">Срок:</span>
        {stage.due_at ? (
          <>
            <span className="tabular-nums text-ink dark:text-ink-dark">{fmtDate(stage.due_at)}</span>
            <Badge tone={stage.urgency}>{URGENCY_LABEL[stage.urgency]}</Badge>
          </>
        ) : (
          <span className="text-ink-secondary dark:text-ink-dark-secondary">
            на этом этапе системный срок не задан
          </span>
        )}
        <span className="text-xs text-ink-muted">· по регламенту кафедры: {stage.catalog_due}</span>
      </div>

      <p className="max-w-3xl text-sm text-ink-secondary dark:text-ink-dark-secondary">{stage.what_to_do}</p>

      <Documents items={stage.documents} />

      {stage.is_mine && (
        <div>
          <Button variant="primary" size="md" onClick={onComplete}>
            Отметить выполненным
          </Button>
        </div>
      )}
    </div>
  );
}

function Documents({ items }) {
  if (!items?.length) return null;
  return (
    <div>
      <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-ink-muted">Что подготовить</div>
      <ul className="flex flex-col gap-1 text-sm text-ink dark:text-ink-dark">
        {items.map((d) => (
          <li key={d} className="flex gap-2">
            <span aria-hidden className="text-ink-muted">
              —
            </span>
            {d}
          </li>
        ))}
      </ul>
    </div>
  );
}

function StageRow({ stage, last }) {
  const [open, setOpen] = useState(false);
  const mark = STAGE_MARK[stage.status] || STAGE_MARK.upcoming;
  return (
    <li className="flex gap-3">
      <div className="flex flex-col items-center">
        <span
          className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 text-xs font-semibold ${mark.ring}`}
          aria-label={mark.label}
        >
          {mark.symbol}
        </span>
        {!last && <span className="w-px flex-1 bg-gridline dark:bg-white/10" />}
      </div>
      <div className="flex-1 pb-4">
        <button onClick={() => setOpen(!open)} className="flex w-full flex-wrap items-center gap-2 text-left">
          <span
            className={`text-sm ${
              stage.status === "current" ? "font-semibold text-ink dark:text-ink-dark" : "text-ink dark:text-ink-dark"
            }`}
          >
            {stage.title}
          </span>
          <span className="text-xs text-ink-muted">{mark.label}</span>
          {stage.is_mine && <Badge tone="accent">ваш шаг</Badge>}
          <span className="ml-auto text-xs text-ink-muted">{open ? "свернуть" : "подробнее"}</span>
        </button>
        <div className="text-xs text-ink-muted">{stage.actor}</div>
        {open && (
          <div className="mt-2 flex flex-col gap-2 rounded-md border border-gridline p-3 dark:border-white/10">
            <p className="text-sm text-ink-secondary dark:text-ink-dark-secondary">{stage.what_to_do}</p>
            <Documents items={stage.documents} />
            <div className="text-xs text-ink-muted">
              По регламенту: {stage.catalog_due} · источник: {stage.source}
            </div>
          </div>
        )}
      </div>
    </li>
  );
}
