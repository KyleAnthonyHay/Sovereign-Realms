using UnrealBuildTool;

public class SovereignRealmsTarget : TargetRules
{
	public SovereignRealmsTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("SovereignRealms");

		// Enable ThinLTO (bPreferThinLTO defaults to true in UE 5.8) for Mac Shipping builds.
		// On an Installed Engine the precompiled Engine .o files remain native arm64 Mach-O, while the game's own
		// translation units get cross-TU inlining and dead-code elimination at modest link-time cost.
		if (Target.Platform == UnrealTargetPlatform.Mac && Target.Configuration == UnrealTargetConfiguration.Shipping)
		{
			bAllowLTCG = true;
			bOverrideBuildEnvironment = true;
		}
	}
}
