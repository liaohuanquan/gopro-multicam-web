import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  applyRecordingConfig,
  cancelCaptureCollection,
  createTaskEvent,
  discoverCameras,
  getCaptureSession,
  getCameras,
  getTaskEvents,
  locateCamera,
  removeCamera,
  renameCamera,
  startCaptureSession,
  stopAndCollectCaptureSession,
} from "../api";
import { formatUtc } from "../taskTime";
import type { BatchCommandResponse, DiscoverCameraInput, TaskEvent } from "../types";

function summarizeResult(result: BatchCommandResponse, successText: string) {
  if (result.failure_count === 0) {
    toast.success(`${result.success_count} 台相机${successText}`);
    return;
  }
  toast.error(`${result.success_count} 台成功，${result.failure_count} 台失败`, {
    description: result.results.filter((item) => !item.success).map((item) => item.message).join("；"),
  });
}

export function useCaptureConsole({ onDiscovered }: { onDiscovered?: () => void } = {}) {
  const queryClient = useQueryClient();
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [taskName, setTaskName] = useState("任务 01");
  const [captureSessionId, setCaptureSessionId] = useState<string | null>(() => window.localStorage.getItem("gopro-multicam.capture-session"));

  const camerasQuery = useQuery({
    queryKey: ["cameras"],
    queryFn: getCameras,
    refetchInterval: 1000,
  });
  const taskEventsQuery = useQuery({
    queryKey: ["task-events"],
    queryFn: getTaskEvents,
    refetchInterval: 1000,
  });
  const captureSessionQuery = useQuery({
    queryKey: ["capture-session", captureSessionId],
    queryFn: () => getCaptureSession(captureSessionId as string),
    enabled: Boolean(captureSessionId),
    refetchInterval: (query) => query.state.data?.status === "collecting" ? 1000 : 3000,
  });

  const cameras = camerasQuery.data ?? [];
  const effectiveSelectedIds = selectedIds.length ? selectedIds : cameras.map((camera) => camera.id);

  const taskEventMutation = useMutation({
    mutationFn: ({ event, active }: { event: "start" | "end"; active: TaskEvent | null }) => createTaskEvent({
      task_id: active?.task_id,
      task_name: active?.task_name ?? taskName.trim(),
      event,
      countdown_seconds: 3,
    }),
    onSuccess: (event) => {
      toast.success(`${event.task_name} ${event.event === "start" ? "开始" : "结束"}切点已记录`, {
        description: `UTC ${formatUtc(event.utc_at)}`,
      });
      queryClient.invalidateQueries({ queryKey: ["task-events"] });
      if (event.event === "end") {
        const starts = taskEventsQuery.data?.events.filter((item) => item.event === "start").length ?? 0;
        setTaskName(`任务 ${String(starts + 1).padStart(2, "0")}`);
      }
    },
    onError: (error: Error) => toast.error("任务切点记录失败", { description: error.message }),
  });

  const startCaptureMutation = useMutation({
    mutationFn: startCaptureSession,
    onSuccess: (session) => {
      setCaptureSessionId(session.id);
      setTaskName("任务 01");
      window.localStorage.setItem("gopro-multicam.capture-session", session.id);
      toast.success("采集已开始", { description: session.id });
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      queryClient.invalidateQueries({ queryKey: ["task-events"] });
    },
    onError: (error: Error) => toast.error("采集启动失败", { description: error.message }),
  });

  const stopAndCollectMutation = useMutation({
    mutationFn: stopAndCollectCaptureSession,
    onSuccess: (session) => {
      queryClient.setQueryData(["capture-session", session.id], session);
      toast.success("录制已停止，正在收集素材");
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
    },
    onError: (error: Error) => toast.error("停止或收集启动失败", { description: error.message }),
  });

  const cancelCollectionMutation = useMutation({
    mutationFn: cancelCaptureCollection,
    onSuccess: (session) => {
      queryClient.setQueryData(["capture-session", session.id], session);
      toast.success("本次素材收集已中断", { description: "已完整下载的文件会保留" });
    },
    onError: (error: Error) => toast.error("中断收集失败", { description: error.message }),
  });

  const recordingConfigMutation = useMutation({
    mutationFn: applyRecordingConfig,
    onSuccess: (result) => {
      summarizeResult(result, "已应用录制参数");
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
    },
    onError: (error: Error) => toast.error("录制参数应用失败", { description: error.message }),
  });

  const discoverMutation = useMutation({
    mutationFn: (input: DiscoverCameraInput) => discoverCameras(input),
    onSuccess: (result) => {
      if (result.discovered_count === 0) {
        toast.error("没有发现相机", { description: "确认相机已完成扫码，并与服务器连接到同一 Wi-Fi。" });
        return;
      }
      toast.success(`已发现 ${result.discovered_count} 台相机并加入设备组`);
      onDiscovered?.();
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
    },
    onError: (error: Error) => toast.error("局域网扫描失败", { description: error.message }),
  });

  const locateMutation = useMutation({
    mutationFn: locateCamera,
    onSuccess: (camera) => toast.success(`${camera.name} 已发出定位提示音`),
    onError: (error: Error) => toast.error("定位信号发送失败", { description: error.message }),
  });

  const removeMutation = useMutation({
    mutationFn: removeCamera,
    onSuccess: () => {
      toast.success("相机已从设备组移除");
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
    },
    onError: (error: Error) => toast.error("移除失败", { description: error.message }),
  });

  const renameMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => renameCamera(id, name),
    onSuccess: (camera) => {
      toast.success(`设备已改名为 ${camera.name}`);
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
    },
    onError: (error: Error) => toast.error("改名失败", { description: error.message }),
  });

  const summary = useMemo(() => ({
    online: cameras.filter((camera) => camera.online).length,
    recording: cameras.filter((camera) => camera.recording).length,
    ready: cameras.filter((camera) => camera.online
      && (camera.battery_percent === null || camera.battery_percent >= 20)
      && (camera.sd_remaining_minutes === null || camera.sd_remaining_minutes >= 10)
      && camera.overheating !== true).length,
  }), [cameras]);

  function toggleCamera(id: string) {
    setSelectedIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  }

  const cameraCommandPending = startCaptureMutation.isPending
    || stopAndCollectMutation.isPending
    || cancelCollectionMutation.isPending
    || recordingConfigMutation.isPending
    || removeMutation.isPending
    || locateMutation.isPending
    || renameMutation.isPending;

  return {
    cameras,
    camerasQuery,
    taskEventsQuery,
    taskName,
    setTaskName,
    selectedIds,
    effectiveSelectedIds,
    summary,
    cameraCommandPending,
    taskEventPending: taskEventMutation.isPending,
    discoverPending: discoverMutation.isPending,
    captureSession: captureSessionQuery.data,
    toggleCamera,
    selectAll: () => setSelectedIds(cameras.map((camera) => camera.id)),
    refreshCameras: () => camerasQuery.refetch(),
    createTaskBoundary: (event: "start" | "end", active: TaskEvent | null) => taskEventMutation.mutate({ event, active }),
    startRecording: () => startCaptureMutation.mutate(effectiveSelectedIds),
    stopRecording: () => {
      if (!captureSessionId) {
        toast.error("没有由当前客户端启动的采集会话");
        return;
      }
      stopAndCollectMutation.mutate(captureSessionId);
    },
    cancelCollection: () => {
      if (!captureSessionId) {
        toast.error("没有可中断的采集会话");
        return;
      }
      if (window.confirm("确认中断本次素材收集？已完整下载的文件会保留。")) {
        cancelCollectionMutation.mutate(captureSessionId);
      }
    },
    applyRecordingConfig: () => recordingConfigMutation.mutate(effectiveSelectedIds),
    applyRecordingConfigAsync: () => recordingConfigMutation.mutateAsync(effectiveSelectedIds),
    startRecordingAsync: () => startCaptureMutation.mutateAsync(effectiveSelectedIds),
    stopRecordingAsync: (sessionId: string) => stopAndCollectMutation.mutateAsync(sessionId),
    discover: (input: DiscoverCameraInput) => discoverMutation.mutate(input),
    locate: (id: string) => locateMutation.mutate(id),
    remove: (id: string) => removeMutation.mutate(id),
    rename: (id: string, name: string) => renameMutation.mutate({ id, name }),
  };
}
