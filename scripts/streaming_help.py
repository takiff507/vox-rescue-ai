"""Print the intended real-time callback contract without opening a device."""

print("Streaming contract: input torch.float32 mono PCM chunk -> output PCM chunk")
print("Use vox_rescue.streaming.StreamingEnhancer with a later mic/WebRTC callback.")
print("No microphone is opened and no network access is performed.")

