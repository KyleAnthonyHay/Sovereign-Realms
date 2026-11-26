using UnrealBuildTool;

public class SovereignRealms : ModuleRules
{
	public SovereignRealms(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicIncludePaths.Add(ModuleDirectory);
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "RenderCore", "RHI", "AIModule", "Slate", "SlateCore", "ApplicationCore" });
		PrivateDependencyModuleNames.AddRange(new string[] { "Json", "MoviePlayer", "UMG" });      // the commander reads the map's json (VLAIWorld.cpp); the loading screen, and FWidgetRenderer for its preview (VLLoadingScreen.cpp)
		PrivateDependencyModuleNames.AddRange(new string[] { "NetCore", "Sockets" });   // multiplayer (VLNet.*): the fast array of buildings; this machine's address for the host's screen
		PrivateDependencyModuleNames.Add("JsonUtilities");     // vl.SaveDump writes the match as JSON (VLSave.cpp)
	}
}
