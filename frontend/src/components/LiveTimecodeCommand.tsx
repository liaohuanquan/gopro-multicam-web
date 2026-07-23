import { useEffect, useState } from "react";

import { buildLiveTimecodeCommand } from "../taskTime";

function getMachineId() {
  const stored = window.localStorage.getItem("MachineId");
  if (stored && /^\d{5}$/.test(stored)) return stored;

  const values = new Uint32Array(1);
  window.crypto.getRandomValues(values);
  const machineId = String(values[0] % 100000).padStart(5, "0");
  window.localStorage.setItem("MachineId", machineId);
  return machineId;
}

export function LiveTimecodeCommand() {
  const [machineId] = useState(getMachineId);
  const [command, setCommand] = useState(() => buildLiveTimecodeCommand(new Date(), machineId));

  useEffect(() => {
    const timer = window.setInterval(() => {
      setCommand(buildLiveTimecodeCommand(new Date(), machineId));
    }, 30);
    return () => window.clearInterval(timer);
  }, [machineId]);

  return (
    <div className="live-timecode-command" aria-live="off">
      <span>QR Command</span>
      <code>{command}</code>
    </div>
  );
}
