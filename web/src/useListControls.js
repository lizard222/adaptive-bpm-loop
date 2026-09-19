import { useEffect, useMemo, useState } from "react";

// Общая логика поиска+сортировки+пагинации для списков «Процессы»/«Задачи» —
// оба экрана получают от API уже полный массив (бэкенд не пагинирует), так
// что разбиение на страницы, поиск и сортировка делаются на клиенте.
//
// searchFn(item, query) -> bool — query уже в нижнем регистре, без пробелов по краям.
// sortOptions — [{key, label, compare(a, b)}], первый элемент — сортировка по умолчанию,
// если defaultSort не передан.
export function useListControls(items, { searchFn, sortOptions, defaultSort, pageSize = 10 }) {
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState(defaultSort || sortOptions[0]?.key);
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? items.filter((item) => searchFn(item, q)) : items;
  }, [items, query, searchFn]);

  const sorted = useMemo(() => {
    const option = sortOptions.find((o) => o.key === sortKey);
    // Без compare (пункт "по умолчанию") — оставляем порядок, в котором
    // прислал бэкенд, не гоняем через Array.sort(undefined) (это дало бы
    // сортировку по строковому представлению, а не "как есть").
    return option?.compare ? [...filtered].sort(option.compare) : filtered;
  }, [filtered, sortKey, sortOptions]);

  const totalCount = sorted.length;
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));
  const currentPage = Math.min(page, totalPages);
  const pageItems = sorted.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  // Сброс на первую страницу при смене запроса/сортировки — иначе легко
  // залипнуть на пустой странице №4, когда результатов поиска стало меньше.
  useEffect(() => {
    setPage(1);
  }, [query, sortKey]);

  return {
    query,
    setQuery,
    sortKey,
    setSortKey,
    page: currentPage,
    setPage,
    totalPages,
    totalCount,
    pageItems,
    pageSize,
  };
}

// Значения без даты (null) — всегда в конец списка, независимо от
// направления сортировки: это честнее, чем молча трактовать "нет данных"
// как условную дату-эпоху.
export function compareByDate(field, direction = "asc") {
  return (a, b) => {
    const av = a[field];
    const bv = b[field];
    if (!av && !bv) return 0;
    if (!av) return 1;
    if (!bv) return -1;
    const diff = new Date(av).getTime() - new Date(bv).getTime();
    return direction === "asc" ? diff : -diff;
  };
}

export function compareByString(field, direction = "asc") {
  return (a, b) => {
    const cmp = String(a[field]).localeCompare(String(b[field]), "ru");
    return direction === "asc" ? cmp : -cmp;
  };
}
