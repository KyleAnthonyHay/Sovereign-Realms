#include "VLPartMesh.h"
#include "HAL/IConsoleManager.h"
#include "StaticMeshSceneProxy.h"

namespace
{
	// (The Mac ran 1 for a day: this module was compiled with RHI_RAYTRACING 0 against a prebuilt engine that has 1, so
	// FVLPartSceneProxy's layout and vtable did not match the engine's. The targets now define it, Source/*.Target.cs.)
	TAutoConsoleVariable<int32> CVarPartOcclusion(TEXT("vl.Opt.PartOcclusion"), 0,
		TEXT("0: a unit's parts take the engine's approximate occlusion, as a static mesh does (a part seen last frame is asked about again one frame in ten or so). 1: a query a part a frame, as before. 2: never asked about (always drawn when in the view). For parts whose render state is made after it is set"));

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
