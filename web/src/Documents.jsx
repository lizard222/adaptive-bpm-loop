import { useState } from "react";
import * as api from "./api.js";
import Card from "./components/Card.jsx";
import Button from "./components/Button.jsx";
import LoadingState from "./components/LoadingState.jsx";
import ErrorState from "./components/ErrorState.jsx";
import EmptyState from "./components/EmptyState.jsx";
import FormField, { Input, Select } from "./components/FormField.jsx";
import { useApiData } from "./useApiData.js";
import { useToast } from "./components/Toast.jsx";
import { fmtDate } from "./format.js";

export default function Documents() {
  // РЕАЛЬНЫЙ ФИКС редизайна: до этого начальная загрузка шаблонов+документов
  // не имела try/catch/loading вообще — сбой здесь раньше проходил
  // незамеченным (единственный экран без обработки ошибок при загрузке).
  const { data, error, loading, refresh } = useApiData(async () => {
    const [t, d] = await Promise.all([api.listDocumentTemplates(), api.listDocuments()]);
    return { templates: t.templates, documents: d.documents };
  });
  const [selected, setSelected] = useState("");
  const [caseId, setCaseId] = useState("");
  const [processKey, setProcessKey] = useState("");
  const [fields, setFields] = useState({});
  const [genError, setGenError] = useState(null);
  const [busy, setBusy] = useState(false);
  const showToast = useToast();

  if (loading) {
    return (
      <Card title="Документы">
        <LoadingState rows={4} />
      </Card>
    );
  }
  if (error) {
    return (
      <Card title="Документы">
        <ErrorState message={error} onRetry={refresh} />
      </Card>
    );
  }

  const templates = data?.templates || [];
  const docs = data?.documents || [];
  const current = selected || templates[0]?.name || "";
  const spec = templates.find((t) => t.name === current);

  async function generate() {
    setBusy(true);
    setGenError(null);
    try {
      await api.generateDocument({ template: current, case_id: caseId, process_key: processKey, context: fields });
      setFields({});
      showToast("Документ сформирован");
      await refresh();
    } catch (e) {
      setGenError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Card title="Сформировать документ">
        {templates.length === 0 ? (
          <EmptyState message="Шаблоны документов не найдены." />
        ) : (
          <div className="flex flex-col gap-3 sm:max-w-md">
            <FormField label="Шаблон">
              <Select value={current} onChange={(e) => setSelected(e.target.value)}>
                {templates.map((t) => (
                  <option key={t.name} value={t.name}>
                    {t.name}
                  </option>
                ))}
              </Select>
            </FormField>
            <FormField label="Экземпляр (case_id)">
              <Input value={caseId} onChange={(e) => setCaseId(e.target.value)} />
            </FormField>
            <FormField label="Процесс (process_key)">
              <Input value={processKey} onChange={(e) => setProcessKey(e.target.value)} />
            </FormField>
            {spec?.required_fields.map((f) => (
              <FormField key={f} label={f}>
                <Input value={fields[f] || ""} onChange={(e) => setFields({ ...fields, [f]: e.target.value })} />
              </FormField>
            ))}
            {genError && <p className="text-sm text-status-critical">{genError}</p>}
            <Button variant="primary" disabled={!current} busy={busy} busyLabel="Формирую…" onClick={generate}>
              Сформировать
            </Button>
          </div>
        )}
      </Card>

      <Card title="Сформированные документы">
        {docs.length === 0 ? (
          <EmptyState message="Документов ещё не формировалось." />
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
                <Button variant="secondary" onClick={() => api.downloadDocument(d.id, `${d.template}_${d.id}.docx`)}>
                  Скачать
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
