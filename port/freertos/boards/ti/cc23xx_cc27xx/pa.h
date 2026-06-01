/*
 * Copyright (c) 2026 Hubble Network, Inc.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#ifndef PORT_FREERTOS_SAT_TI_PA_H
#define PORT_FREERTOS_SAT_TI_PA_H

#if defined(DeviceFamily_CC23X0R5)
#define TI_PA_DEFAULT_DBM 0U
#else
#error "Device not supported"
#endif

#endif /* PORT_FREERTOS_SAT_TI_PA_H */
