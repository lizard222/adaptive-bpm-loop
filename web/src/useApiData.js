import { useCallback, useEffect, useState } from "react";

// Простой хук данных без внешней библиотеки (react-query и т.п. осознанно
// не вводится — экранов, реально нуждающихся в общем кеше между собой,
// пока два: Overview/Processes оба дёргают getDashboardSummary()
// независимо; если число таких дублирующихся источников вырастет,
// имеет смысл вынести это в общий контекст, но не сейчас).
//
// Даёт единообразные loading/error/retry ВСЕМ экранам — раньше это было
// продублировано по-разному в каждом файле, а в Documents.jsx для
// начальной загрузки не было вообще никакой обработки ошибок.
export function useApiData(fetcher, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const result = await fetcher();
      setData(result);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { data, error, loading, refresh, setData };
}
