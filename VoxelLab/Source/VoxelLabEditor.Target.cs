using UnrealBuildTool;

public class VoxelLabEditorTarget : TargetRules
{
	public VoxelLabEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("VoxelLab");
	}
}
