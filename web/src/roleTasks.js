// Соответствие "какие task_name видит какая роль" — временная, явно
// задокументированная замена настоящих BPMN-дорожек (api/tasks.py
// намеренно не фильтрует список по роли: BPMN-модели прототипа пока не
// размечены дорожками для ролей в общем виде — см. докстринг api/tasks.py).
// normcontrol — единственная роль, у которой сейчас есть РОВНО один
// осмысленный шаг (mining/control_points.VKR_DEFENSE_CONTROL_POINTS,
// bpmn/demo/vkr_defense.bpmn: задача "normcontrol") — фильтр здесь
// достаточен для одного role/task_name соответствия и не пытается решить
// общую задачу дорожек (это T-25/T-22/T-23). Роль, для которой фильтр не
// задан, видит все READY-задачи без изменений — поведение остальных ролей
// не затронуто.
export const ROLE_TASK_FILTER = {
  normcontrol: ["normcontrol"],
};

export function visibleTasks(tasks, role) {
  const allowed = ROLE_TASK_FILTER[role];
  return allowed ? tasks.filter((t) => allowed.includes(t.task_name)) : tasks;
}
