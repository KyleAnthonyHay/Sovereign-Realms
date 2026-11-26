using UnrealBuildBase;
using UnrealBuildTool;

public class SovereignRealmsEditorTarget : TargetRules
{
	public SovereignRealmsEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
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
	}
}
