#pragma once

#include "CoreMinimal.h"

DECLARE_LOG_CATEGORY_EXTERN(LogSovereignRealms, Log, All);

// The name of the Alt key as the HUD writes it: "Option" on a Mac keyboard, "Alt" elsewhere (the key itself is the
// same EKeys::LeftAlt / RightAlt on both). A string literal, to sit between two TEXT("...") pieces.
#if PLATFORM_MAC
#define VL_ALT_KEY TEXT("Option")
#else
#define VL_ALT_KEY TEXT("Alt")
#endif
