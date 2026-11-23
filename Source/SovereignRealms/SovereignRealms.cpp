#include "SovereignRealms.h"
#include "VLLoadingScreen.h"
#include "Modules/ModuleManager.h"
#if PLATFORM_MAC
#include "Async/Fundamental/Scheduler.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformMisc.h"
#include "Misc/App.h"
#include "RenderingThread.h"
#include "RHICommandList.h"
#include <pthread/qos.h>
#include <sys/sysctl.h>
#endif

DEFINE_LOG_CATEGORY(LogSovereignRealms);

namespace
{
#if PLATFORM_MAC
	TAutoConsoleVariable<int32> CVarMacWorkers(TEXT("vl.Opt.MacWorkers"), 1,
		TEXT("1: lift UE's 4-worker game cap on Apple Silicon by sizing foreground workers to P-cores and background workers to E-cores. 0: engine default."));
	TAutoConsoleVariable<int32> CVarMacQoS(TEXT("vl.Opt.MacQoS"), 1,
		TEXT("1: set QOS_CLASS_USER_INTERACTIVE on Game, Render and RHI threads so macOS XNU keeps frame-critical threads on P-cores. 0: engine default."));

	int32 ReadSysctlInt(const char* Name)
	{
		int32 Value = 0;
		size_t Size = sizeof(Value);
		return sysctlbyname(Name, &Value, &Size, nullptr, 0) == 0 ? Value : 0;
	}

	void ApplyAppleSiliconThreading()
	{
		static bool bApplied = false;
		if (bApplied)
		{
			return;
		}
		bApplied = true;

		if (CVarMacQoS.GetValueOnGameThread() != 0)
		{
			pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);
			ENQUEUE_RENDER_COMMAND(VLMacRenderThreadQoS)([](FRHICommandListImmediate& RHICmdList)
			{
				pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);
				RHICmdList.EnqueueLambda([](FRHICommandListImmediate&)
				{
					pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);
				});
			});
			UE_LOG(LogSovereignRealms, Log, TEXT("apple-silicon: promoted Game/Render/RHI threads to QOS_CLASS_USER_INTERACTIVE"));
		}

		// Only resize workers in standalone Game/Shipping runs (never mutate Editor/PIE scheduler pools).
		if (!GIsEditor && IsRunningGame() && CVarMacWorkers.GetValueOnGameThread() != 0)
		{
			const int32 PCores = ReadSysctlInt("hw.perflevel0.physicalcpu");
			const int32 ECores = ReadSysctlInt("hw.perflevel1.physicalcpu");
			if (PCores > 0)
			{
				// Reserve ~2 P-cores for GameThread + RenderThread/RHIThread; scale remaining P-cores to foreground
				// workers and E-cores to background workers (UE's FGenericPlatformMisc caps Shipping at 4 total).
				const uint32 Foreground = static_cast<uint32>(FMath::Clamp(PCores - 2, 2, 6));
				const uint32 Background = static_cast<uint32>(FMath::Clamp(ECores > 0 ? ECores : 2, 2, 8));
				const uint32 Current = LowLevelTasks::FScheduler::Get().GetNumWorkers();
				if (Foreground + Background > Current)
				{
					LowLevelTasks::FScheduler::Get().RestartWorkers(Foreground, Background);
					UE_LOG(LogSovereignRealms, Log, TEXT("apple-silicon: workers %u -> %u (%u FG on %d P-cores, %u BG on %d E-cores)"),
						Current, Foreground + Background, Foreground, PCores, Background, ECores);
				}
			}
		}
	}
#endif
}

class FSovereignRealmsModule : public FDefaultGameModuleImpl
{
public:
	virtual void StartupModule() override
	{
		VLLoadingScreen::Startup();
#if PLATFORM_MAC
		PostWorldInitHandle = FWorldDelegates::OnPostWorldInitialization.AddLambda([](UWorld* World, const UWorld::InitializationValues)
		{
			if (World && (World->WorldType == EWorldType::Game || World->WorldType == EWorldType::PIE))
			{
				ApplyAppleSiliconThreading();
			}
		});
#endif
	}

	virtual void ShutdownModule() override
	{
		VLLoadingScreen::Shutdown();
#if PLATFORM_MAC
		if (PostWorldInitHandle.IsValid())
		{
			FWorldDelegates::OnPostWorldInitialization.Remove(PostWorldInitHandle);
			PostWorldInitHandle.Reset();
		}
#endif
	}

private:
#if PLATFORM_MAC
	FDelegateHandle PostWorldInitHandle;
#endif
};

IMPLEMENT_PRIMARY_GAME_MODULE(FSovereignRealmsModule, SovereignRealms, "SovereignRealms");
