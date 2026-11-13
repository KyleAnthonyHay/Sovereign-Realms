// Copyright Sovereign Realms.

using UnrealBuildTool;

public class SovereignRealmsEditorTarget : TargetRules
{
	public SovereignRealmsEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("SovereignRealms");
	}
}
