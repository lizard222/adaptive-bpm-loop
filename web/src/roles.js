// Единая точка правды для ролевых проверок UI — было продублировано
// (App.jsx и Overview.jsx проверяли "dept_head"/"admin" каждый по-своему).
// Списки зеркалят require_role(...) на бэкенде — держать их синхронно с
// api/corrections.py и api/processes.py при изменении ролей.
export const CAN_SEE_CORRECTIONS = ["dept_head", "admin"];
export const CAN_LAUNCH_PROCESS = ["dept_head", "secretary", "admin"];

export function hasRole(user, allowed) {
  return !!user && allowed.includes(user.role);
}
