using UnrealBuildBase;
using UnrealBuildTool;

public class SovereignRealmsTarget : TargetRules
{
	public SovereignRealmsTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("SovereignRealms");

		// Mac, installed (launcher) engine: compile this project's code with the RHI_RAYTRACING the prebuilt engine has.
		// Config/Mac/MacEngine.ini turns bEnableRayTracing off (so that no ray-tracing shaders or mesh data are cooked),
		// and UnrealBuildTool takes RHI_RAYTRACING from that same setting: 0 for what it compiles here, while the
		// engine's prebuilt objects were compiled with 1. The headers the two share differ under that macro.
		// FPrimitiveSceneProxy declares virtual functions inside #if RHI_RAYTRACING, so a proxy class of this project
		// had every later vtable slot shifted (the renderer calling HasRayTracingRepresentation() ran another function:
		// the arrow trails' proxy crashed the render thread in FScene::Update as the first arrow flew), and
		// FStaticMeshSceneProxy has members there (the units' parts' proxy, VLPartMesh.cpp). An engine built from source
		// follows the ini itself and needs none of this.
		if (Target.Platform == UnrealTargetPlatform.Mac && Unreal.IsEngineInstalled())
		{
			GlobalDefinitions.Add("RHI_RAYTRACING=1");
			bOverrideBuildEnvironment = true;
		}

		// Enable ThinLTO (bPreferThinLTO defaults to true in UE 5.8) for Mac Shipping builds.
		// On an Installed Engine the precompiled Engine .o files remain native arm64 Mach-O, while the game's own
		// translation units get cross-TU inlining and dead-code elimination at modest link-time cost.
		if (Target.Platform == UnrealTargetPlatform.Mac && Target.Configuration == UnrealTargetConfiguration.Shipping)
		{
			bAllowLTCG = true;
			bOverrideBuildEnvironment = true;
		}
		// Win64 Shipping keeps the engine's defaults, on purpose. With an installed (launcher) engine the engine's
		// own objects are prebuilt, so anything that changes the build environment needs bOverrideBuildEnvironment;
		// MSVC's link-time code generation over them (bAllowLTCG) multiplies the link time for a gain confined to this
		// module's few hot loops, and is not measured yet (Docs/Optimization/Windows/PROPOSAL.md, "Not done").
		// What a Windows Shipping build needs is done by the packaging instead (Tools/windows/package.ps1): the
		// symbols are separate .pdb files there, so nothing has to be stripped from the executable.
	}
}
