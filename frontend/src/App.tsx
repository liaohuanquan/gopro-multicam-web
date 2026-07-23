import { useState } from "react";

import { OnboardingDialog } from "./OnboardingDialog";
import { RecordingConfigDialog } from "./components/RecordingConfigDialog";
import { AppSidebar } from "./components/AppSidebar";
import { CameraSection } from "./components/CameraSection";
import { ControlDock } from "./components/ControlDock";
import { TaskConsole } from "./components/TaskConsole";
import { WorkspaceHeader } from "./components/WorkspaceHeader";
import { SyncValidationDialog } from "./components/SyncValidationDialog";
import { useCaptureConsole } from "./hooks/useCaptureConsole";
import type { CameraStatus } from "./types";

const TIMECODE_URL = "https://gopro.github.io/labs/control/precisiontime_utc/";

export default function App() {
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [recordingConfigOpen, setRecordingConfigOpen] = useState(false);
  const [syncValidationOpen, setSyncValidationOpen] = useState(false);
  const capture = useCaptureConsole({ onDiscovered: () => setOnboardingOpen(false) });

  function renameCamera(camera: CameraStatus) {
    const name = window.prompt("输入新的设备名称", camera.name)?.trim();
    if (name && name !== camera.name) capture.rename(camera.id, name);
  }

  function removeCamera(camera: CameraStatus) {
    if (window.confirm(`确认将 ${camera.name} 从设备组移除？`)) capture.remove(camera.id);
  }

  const hasCameras = capture.cameras.length > 0;
  const cameraControlsDisabled = capture.cameraCommandPending || !hasCameras;
  const sessionRecording = capture.captureSession?.status === "recording";
  const sessionCollecting = capture.captureSession?.status === "collecting";

  return (
    <main className="app-shell">
      <AppSidebar
        summary={capture.summary}
        total={capture.cameras.length}
        timecodeUrl={TIMECODE_URL}
      />

      <div className="workspace">
        <WorkspaceHeader onAddCamera={() => setOnboardingOpen(true)} />
        {sessionRecording && (
          <TaskConsole
            data={capture.taskEventsQuery.data}
            taskName={capture.taskName}
            onTaskNameChange={capture.setTaskName}
            pending={capture.taskEventPending}
            onCreateEvent={capture.createTaskBoundary}
          />
        )}
        <CameraSection
          cameras={capture.cameras}
          selectedIds={capture.effectiveSelectedIds}
          loadingError={capture.camerasQuery.isError}
          onAddCamera={() => setOnboardingOpen(true)}
          onSelectAll={capture.selectAll}
          onRefresh={capture.refreshCameras}
          onOpenRecordingConfig={() => setRecordingConfigOpen(true)}
          onOpenSyncValidation={() => setSyncValidationOpen(true)}
          applyDisabled={cameraControlsDisabled || sessionRecording || sessionCollecting}
          onToggle={capture.toggleCamera}
          onLocate={capture.locate}
          onRename={renameCamera}
          onRemove={removeCamera}
        />
      </div>

      <ControlDock
        cameraCount={capture.effectiveSelectedIds.length}
        explicitlySelected={capture.selectedIds.length > 0}
        session={capture.captureSession}
        startDisabled={cameraControlsDisabled || sessionRecording || sessionCollecting}
        stopDisabled={cameraControlsDisabled || !sessionRecording}
        onStart={capture.startRecording}
        onStop={capture.stopRecording}
        onCancel={capture.cancelCollection}
      />

      <OnboardingDialog
        open={onboardingOpen}
        pending={capture.discoverPending}
        onClose={() => setOnboardingOpen(false)}
        onDiscover={capture.discover}
      />
      <RecordingConfigDialog
        open={recordingConfigOpen}
        selectedCount={capture.effectiveSelectedIds.length}
        onClose={() => setRecordingConfigOpen(false)}
        onApply={() => capture.applyRecordingConfig()}
      />
      <SyncValidationDialog
        open={syncValidationOpen}
        cameraCount={capture.effectiveSelectedIds.length}
        onClose={() => setSyncValidationOpen(false)}
        onApply={capture.applyRecordingConfigAsync}
        onStart={capture.startRecordingAsync}
        onStop={capture.stopRecordingAsync}
      />
    </main>
  );
}
