#include "VLPartMesh.h"
#include "HAL/IConsoleManager.h"
#include "StaticMeshSceneProxy.h"

namespace
{
	// Mac: 1 (the engine's own proxy). Config/Mac/MacEngine.ini turns bEnableRayTracing off, so this module is built
	// with RHI_RAYTRACING 0 while the prebuilt engine has it on: FStaticMeshSceneProxy's ray-tracing members then sit
	// at different offsets on the two sides, and a subclass made here crashed the renderer as the first unit spawned
	// (FPrimitiveSceneInfo's constructor, the editor and packaged builds alike). Windows keeps 0.
#if PLATFORM_MAC
	constexpr int32 DefaultPartOcclusion = 1;
#else
	constexpr int32 DefaultPartOcclusion = 0;
#endif
	TAutoConsoleVariable<int32> CVarPartOcclusion(TEXT("vl.Opt.PartOcclusion"), DefaultPartOcclusion,
		TEXT("(default 0; 1 on the Mac) 0: a unit's parts take the engine's approximate occlusion, as a static mesh does (a part seen last frame is asked about again one frame in ten or so). 1: a query a part a frame, as before. 2: never asked about (always drawn when in the view). For parts whose render state is made after it is set"));

	class FVLPartSceneProxy final : public FStaticMeshSceneProxy
	{
	public:
		FVLPartSceneProxy(UStaticMeshComponent* Component, bool bNeverOccluded)
			: FStaticMeshSceneProxy(Component, false), bNever(bNeverOccluded)
		{
			// what a primitive that does not move gets from the engine by itself (FPrimitiveSceneProxy's constructor)
			bAllowApproximateOcclusion = true;
		}
		virtual bool CanBeOccluded() const override { return !bNever && FStaticMeshSceneProxy::CanBeOccluded(); }

	private:
		bool bNever;
	};
}

FPrimitiveSceneProxy* UVLPartMeshComponent::CreateStaticMeshSceneProxy(Nanite::FMaterialAudit& NaniteMaterials, bool bCreateNanite)
{
	const int32 Mode = CVarPartOcclusion.GetValueOnGameThread();
	if (bCreateNanite || Mode == 1)
	{
		return Super::CreateStaticMeshSceneProxy(NaniteMaterials, bCreateNanite);
	}
	return ::new FVLPartSceneProxy(this, Mode == 2);
}
