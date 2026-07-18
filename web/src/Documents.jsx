import { useEffect, useState } from "react";
import * as api from "./api.js";
import { fmtDate } from "./format.js";

export default function Documents() {
  const [templates, setTemplates] = useState([]);
  const [selected, setSelected] = useState("");
  const [caseId, setCaseId] = useState("");
  const [processKey, setProcessKey] = useState("");
  const [fields, setFields] = useState({});
  const [docs, setDocs] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    const [t, d] = await Promise.all([api.listDocumentTemplates(), api.listDocuments()]);
    setTemplates(t.templates);
    setDocs(d.documents);
    if (!selected && t.templates.length) setSelected(t.templates[0].name);
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const spec = templates.find((t) => t.name === selected);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      await api.generateDocument({ template: selected, case_id: caseId, process_key: processKey, context: fields });
      setFields({});
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <section className="rounded-lg border border-gridline bg-surface p-5 dark:border-white/10 dark:bg-surface-dark">
        <h2 className="mb-4 text-base font-semibold text-ink dark:text-ink-dark">Сформировать документ</h2>
        <div className="flex flex-col gap-3 sm:max-w-md">
          <label className="text-xs text-ink-muted">
            Шаблон
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              className="mt-1 w-full rounded-md border border-gridline bg-page px-2 py-1.5 text-sm text-ink dark:border-white/10 dark:bg-page-dark dark:text-ink-dark"
            >
              {templates.map((t) => (
                <option key={t.name} value={t.name}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-ink-muted">
            Экземпляр (case_id)
            <input
              value={caseId}
              onChange={(e) => setCaseId(e.target.value)}
              className="mt-1 w-full rounded-md border border-gridline bg-page px-2 py-1.5 text-sm text-ink dark:border-white/10 dark:bg-page-dark dark:text-ink-dark"
            />
          </label>
          <label className="text-xs text-ink-muted">
            Процесс (process_key)
            <input
              value={processKey}
              onChange={(e) => setProcessKey(e.target.value)}
              className="mt-1 w-full rounded-md border border-gridline bg-page px-2 py-1.5 text-sm text-ink dark:border-white/10 dark:bg-page-dark dark:text-ink-dark"
            />
          </label>
          {spec?.required_fields.map((f) => (
            <label key={f} className="text-xs text-ink-muted">
              {f}
              <input
                value={fields[f] || ""}
                onChange={(e) => setFields({ ...fields, [f]: e.target.value })}
                className="mt-1 w-full rounded-md border border-gridline bg-page px-2 py-1.5 text-sm text-ink dark:border-white/10 dark:bg-page-dark dark:text-ink-dark"
              />
            </label>
          ))}
          {error && <p className="text-sm text-status-critical">{error}</p>}
          <button
            disabled={busy || !selected}
            onClick={generate}
            className="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-white hover:brightness-110 disabled:opacity-60 dark:bg-accent-dark"
          >
            {busy ? "Формирую…" : "Сформировать"}
          </button>
        </div>
      </section>

      <section className="rounded-lg border border-gridline bg-surface p-5 dark:border-white/10 dark:bg-surface-dark">
        <h2 className="mb-4 text-base font-semibold text-ink dark:text-ink-dark">Сформированные документы</h2>
        {docs.length === 0 ? (
          <p className="py-6 text-center text-sm text-ink-muted">Документов ещё не формировалось.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {docs.map((d) => (
              <li
                key={d.id}
                className="flex flex-wrap items-center gap-2 border-b border-gridline py-2 text-sm last:border-0 dark:border-white/10"
              >
                <span className="font-mono text-xs text-ink-muted">
                  {d.process_key} / {d.case_id}
                </span>
                <span className="text-ink dark:text-ink-dark">{d.template}</span>
                <span className="ml-auto text-xs text-ink-muted">
                  {d.generated_by} · {fmtDate(d.generated_at)}
                </span>
                <button
                  onClick={() => api.downloadDocument(d.id, `${d.template}_${d.id}.docx`)}
                  className="rounded-md border border-gridline px-2 py-1 text-xs font-medium text-ink-secondary hover:bg-page dark:border-white/10 dark:text-ink-dark-secondary dark:hover:bg-white/5"
                >
                  Скачать
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
