using UnrealBuildTool;

public class VoxelLab : ModuleRules
{
	public VoxelLab(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicIncludePaths.Add(ModuleDirectory);
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "RenderCore", "RHI", "AIModule", "Slate", "SlateCore", "ApplicationCore" });
		PrivateDependencyModuleNames.AddRange(new string[] { "Json" });      // the commander reads the map's json (VLAIWorld.cpp)
	}
}
