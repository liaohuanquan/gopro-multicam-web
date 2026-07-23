import type { TaskEvent } from "./types";

export function findActiveTask(events: TaskEvent[]) {
  let active: TaskEvent | null = null;
  for (const event of events) {
    if (event.event === "start") active = event;
    if (event.event === "end" && active?.task_id === event.task_id) active = null;
  }
  return active;
}

export function formatUtc(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "UTC",
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: 3,
  }).format(new Date(value));
}

export function buildLiveTimecodeCommand(date: Date, machineId: string) {
  const part = (value: number, length = 2) => String(value).padStart(length, "0");
  return [
    "oT",
    part(date.getUTCFullYear() - 2000),
    part(date.getUTCMonth() + 1),
    part(date.getUTCDate()),
    part(date.getUTCHours()),
    part(date.getUTCMinutes()),
    part(date.getUTCSeconds()),
    ".",
    part(date.getUTCMilliseconds(), 3),
    "oTI",
    machineId,
  ].join("");
}
