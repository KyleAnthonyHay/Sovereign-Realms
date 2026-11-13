// Copyright Sovereign Realms.

using UnrealBuildTool;

public class SovereignRealmsTarget : TargetRules
{
	public SovereignRealmsTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("SovereignRealms");
	}
}
