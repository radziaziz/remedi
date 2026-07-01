// REMEDI - Web Dashboard Logic (Daily Trends, Buffers & Bulk Adjustments)
document.addEventListener("DOMContentLoaded", () => {
    
    // Helper to format numbers with commas for thousands
    function formatNumber(num) {
        if (num === null || num === undefined) return "";
        return Math.round(Number(num)).toLocaleString('en-US');
    }
    
    // Core State Variables
    let currentSessionId = null;
    let currentTheme = localStorage.getItem("remedi-theme") || "light";
    let activeChartFacility = "HKM";
    let activeChartMedication = "Amlodipine";
    
    // Bulk Adjustment State
    let activeBulkQuantile = "p50";
    let bulkMultiplier = 1.0;
    
    // Chart instances
    let lineChartInstance = null;
    let barChartInstance = null;
    
    // Map instance
    let remediMap = null;
    let mapMarkers = [];
    let mapLines = [];
    let tileLayerInstance = null;
    
    // Raw API data caches
    let rawStateCache = null;
    let originalAllocationData = null; // stock_allocation_district at p50
    let computedSurgeData = null; // medication_surge_district

    // DOM Elements
    const docHtml = document.documentElement;
    const btnThemeToggle = document.getElementById("btn-theme-toggle");
    const themeToggleIcon = document.getElementById("theme-toggle-icon");
    const themeToggleText = document.getElementById("theme-toggle-text");
    
    // Stepper indicators
    const step1Ind = document.getElementById("step-1-indicator");
    const step2Ind = document.getElementById("step-2-indicator");
    const step3Ind = document.getElementById("step-3-indicator");
    
    // Screens
    const screenIngestion = document.getElementById("screen-ingestion");
    const screenAnalysis = document.getElementById("screen-analysis");
    const screenDispatch = document.getElementById("screen-dispatch");
    
    // Ingestion elements
    const workflowStatus = document.getElementById("workflow-status");
    const alertTextInput = document.getElementById("alert-text-input");
    const btnSubmitAlert = document.getElementById("btn-submit-alert");
    const ingestionResultBox = document.getElementById("ingestion-result-box");
    const triageStatusTitle = document.getElementById("triage-status-title");
    const triageStatusDesc = document.getElementById("triage-status-desc");
    const btnProceedToAnalysis = document.getElementById("btn-proceed-to-analysis");
    
    // Analysis elements
    const governanceCard = document.getElementById("governance-card");
    const govStatusText = document.getElementById("gov-status-text");
    const govStatusIcon = document.getElementById("gov-status-icon");
    const govBadgeStatus = document.getElementById("gov-badge-status");
    const govReasonText = document.getElementById("gov-reason-text");
    
    const gisFacility = document.getElementById("gis-facility");
    const gisPopulation = document.getElementById("gis-population");
    const gisVulnerability = document.getElementById("gis-vulnerability");
    
    // Toggles for charts
    const btnChartHkm = document.getElementById("btn-chart-hkm");
    const btnChartHkp = document.getElementById("btn-chart-hkp");
    const btnMedAml = document.getElementById("btn-med-aml");
    const btnMedPer = document.getElementById("btn-med-per");
    const btnMedSim = document.getElementById("btn-med-sim");
    
    // Bulk controls
    const btnBulkP10 = document.getElementById("btn-bulk-p10");
    const btnBulkP50 = document.getElementById("btn-bulk-p50");
    const btnBulkP90 = document.getElementById("btn-bulk-p90");
    const bulkSlider = document.getElementById("bulk-slider");
    const bulkSliderVal = document.getElementById("bulk-slider-val");
    
    // Table body
    const actionPlanTableBody = document.querySelector("#action-plan-table-body tbody");
    const btnApproveActionPlan = document.getElementById("btn-approve-action-plan");
    const btnShowModifyForm = document.getElementById("btn-show-modify-form");
    
    const modificationFormContainer = document.getElementById("modification-form-container");
    const modifyFeedbackInput = document.getElementById("modify-feedback-input");
    const btnSubmitModification = document.getElementById("btn-submit-modification");
    const btnCancelModify = document.getElementById("btn-cancel-modify");
    
    // Dispatch/Screen 3 elements
    const postSafetyReasonText = document.getElementById("post-safety-reason-text");
    const dispatchHkmCard = document.getElementById("dispatch-hkm-card");
    const dispatchHkpCard = document.getElementById("dispatch-hkp-card");
    const btnRestartWizard = document.getElementById("btn-restart-wizard");

    // ==========================================
    // Initialization & Theme Handling
    // ==========================================
    applyTheme(currentTheme);

    btnThemeToggle.addEventListener("click", () => {
        const nextTheme = currentTheme === "light" ? "dark" : "light";
        applyTheme(nextTheme);
    });

    function applyTheme(theme) {
        currentTheme = theme;
        localStorage.setItem("remedi-theme", theme);
        docHtml.setAttribute("data-theme", theme);
        
        if (theme === "dark") {
            themeToggleIcon.innerText = "🌙";
            themeToggleText.innerText = "Dark Mode";
        } else {
            themeToggleIcon.innerText = "☀️";
            themeToggleText.innerText = "Light Mode";
        }
        
        updateMapTileLayer(theme);
        
        // Re-draw charts with updated theme colors if active
        if (rawStateCache) {
            renderCharts(activeChartFacility, activeChartMedication);
        }
    }

    // ==========================================
    // Navigation / Stepper Wizards
    // ==========================================
    function transitionToScreen(stepNum) {
        toggleElement(screenIngestion, false);
        toggleElement(screenAnalysis, false);
        toggleElement(screenDispatch, false);
        
        step1Ind.classList.remove("active", "completed");
        step2Ind.classList.remove("active", "completed");
        step3Ind.classList.remove("active", "completed");
        
        if (stepNum === 1) {
            toggleElement(screenIngestion, true);
            step1Ind.classList.add("active");
        } else if (stepNum === 2) {
            toggleElement(screenAnalysis, true);
            step1Ind.classList.add("completed");
            step2Ind.classList.add("active");
            
            if (remediMap) {
                setTimeout(() => remediMap.invalidateSize(), 100);
            }
        } else if (stepNum === 3) {
            toggleElement(screenDispatch, true);
            step1Ind.classList.add("completed");
            step2Ind.classList.add("completed");
            step3Ind.classList.add("active");
        }
        
        // Auto-scroll to top on wizard transition
        window.scrollTo({ top: 0, behavior: "smooth" });
    }

    // ==========================================
    // Event Handlers
    // ==========================================
    btnSubmitAlert.addEventListener("click", handleStartForecast);
    btnProceedToAnalysis.addEventListener("click", () => transitionToScreen(2));
    
    // Chart Facility buttons
    btnChartHkm.addEventListener("click", () => switchChartFacility("HKM"));
    btnChartHkp.addEventListener("click", () => switchChartFacility("HKP"));
    
    // Chart Medication buttons
    btnMedAml.addEventListener("click", () => switchChartMedication("Amlodipine"));
    btnMedPer.addEventListener("click", () => switchChartMedication("Perindopril"));
    btnMedSim.addEventListener("click", () => switchChartMedication("Simvastatin"));
    
    // Bulk Quantile buttons
    btnBulkP10.addEventListener("click", () => switchBulkQuantile("p10"));
    btnBulkP50.addEventListener("click", () => switchBulkQuantile("p50"));
    btnBulkP90.addEventListener("click", () => switchBulkQuantile("p90"));
    
    // Slider
    bulkSlider.addEventListener("input", handleSliderChange);
    
    btnShowModifyForm.addEventListener("click", () => toggleElement(modificationFormContainer, true));
    btnCancelModify.addEventListener("click", () => toggleElement(modificationFormContainer, false));
    btnSubmitModification.addEventListener("click", handleModifyRequest);
    
    btnApproveActionPlan.addEventListener("click", handleApproveRequest);
    btnRestartWizard.addEventListener("click", resetWizardState);
    
    // Back buttons
    const btnBackToStep1 = document.getElementById("btn-back-to-step-1");
    const btnBackToStep2 = document.getElementById("btn-back-to-step-2");
    if (btnBackToStep1) btnBackToStep1.addEventListener("click", () => transitionToScreen(1));
    if (btnBackToStep2) btnBackToStep2.addEventListener("click", () => transitionToScreen(2));

    // ==========================================
    // Step 1 Ingestion Logic
    // ==========================================
    async function handleStartForecast() {
        const alertText = alertTextInput.value.trim();
        if (!alertText) {
            alert("Please enter a raw disaster warning text alert.");
            return;
        }

        updateWorkflowStatus("running", "ANALYSING ALERT...");
        btnSubmitAlert.disabled = true;
        toggleElement(ingestionResultBox, false);
        toggleElement(btnProceedToAnalysis, false);

        try {
            const res = await apiCall("/api/start", { alert: alertText });
            currentSessionId = res.session_id;
            
            const state = res.state || {};
            const isOutOfCatchment = state.out_of_catchment || state.severity === 0;
            
            triageStatusTitle.innerText = isOutOfCatchment 
                ? "⚠️ Catchment Warning: Out of Catchment" 
                : "✓ Catchment Validated: Makar District Affected";
            triageStatusDesc.innerText = isOutOfCatchment 
                ? "The parsed alert is outside the geographic catchment bounds of Makar District, Pahang. Baseline stock operations continue normally." 
                : `Ingested disaster alert. Coordinator resolved district as '${state.district_name}' with severity rating of ${state.severity.toFixed(2)} (${state.forecast_days}-day horizon).`;
            
            if (isOutOfCatchment) {
                ingestionResultBox.style.borderColor = "var(--warning-color)";
                ingestionResultBox.style.background = "rgba(245, 158, 11, 0.04)";
                toggleElement(btnProceedToAnalysis, false);
            } else {
                ingestionResultBox.style.borderColor = "var(--success-color)";
                ingestionResultBox.style.background = "rgba(16, 185, 129, 0.04)";
                toggleElement(btnProceedToAnalysis, true);
            }
            
            toggleElement(ingestionResultBox, true);
            updateWorkflowStatus("idle", "IDLE");
            
            cacheAndLoadState(res);
        } catch (err) {
            alert("Ingestion pipeline failed: " + err.message);
            updateWorkflowStatus("idle", "IDLE");
        } finally {
            btnSubmitAlert.disabled = false;
        }
    }

    // ==========================================
    // Step 2 Analytics & Data Caching
    // ==========================================
    function cacheAndLoadState(res) {
        rawStateCache = res.state || {};
        
        computedSurgeData = rawStateCache.medication_surge_district || {};
        originalAllocationData = rawStateCache.stock_allocation_district || {};
        
        // Reset Bulk Adjustment states
        activeBulkQuantile = "p50";
        bulkMultiplier = 1.0;
        bulkSlider.value = 100;
        bulkSliderVal.innerText = "100%";
        updateBulkButtonUI();

        // Load GIS Metadata
        gisFacility.innerText = rawStateCache.district_name || "Makar District";
        gisPopulation.innerText = "400,000";
        gisVulnerability.innerText = rawStateCache.severity ? rawStateCache.severity.toFixed(2) : "0.00";
        
        // Load Governance compliance status
        if (rawStateCache.governance_passed) {
            const passed = rawStateCache.governance_passed === "Pass";
            govStatusText.innerText = passed ? "PASSED" : "FAILED";
            govStatusIcon.innerText = passed ? "✓" : "✗";
            
            if (passed) {
                govBadgeStatus.style.color = "var(--success-color)";
                govStatusIcon.style.backgroundColor = "var(--success-color)";
                governanceCard.style.borderColor = "rgba(16, 185, 129, 0.15)";
                governanceCard.style.background = "rgba(16, 185, 129, 0.02)";
            } else {
                govBadgeStatus.style.color = "var(--danger-color)";
                govStatusIcon.style.backgroundColor = "var(--danger-color)";
                governanceCard.style.borderColor = "rgba(239, 68, 68, 0.15)";
                governanceCard.style.background = "rgba(239, 68, 68, 0.02)";
            }
            govReasonText.innerText = rawStateCache.governance_reason || "";
        }
        
        // Render GIS Map
        renderLogisticsMap(originalAllocationData);
        
        // Render Charts (Daily Utilisation & Stock Projection)
        renderCharts(activeChartFacility, activeChartMedication);
        
        // Render editable Action Plan Grid
        recalculateAndRenderTable();
    }

    // ==========================================
    // Switch Toggles (Charts)
    // ==========================================
    function switchChartFacility(facilityId) {
        activeChartFacility = facilityId;
        
        if (facilityId === "HKM") {
            btnChartHkm.classList.add("active");
            btnChartHkp.classList.remove("active");
        } else {
            btnChartHkp.classList.add("active");
            btnChartHkm.classList.remove("active");
        }
        
        renderCharts(activeChartFacility, activeChartMedication);
    }

    function switchChartMedication(medName) {
        activeChartMedication = medName;
        
        btnMedAml.classList.remove("active");
        btnMedPer.classList.remove("active");
        btnMedSim.classList.remove("active");
        
        if (medName === "Amlodipine") btnMedAml.classList.add("active");
        else if (medName === "Perindopril") btnMedPer.classList.add("active");
        else if (medName === "Simvastatin") btnMedSim.classList.add("active");
        
        renderCharts(activeChartFacility, activeChartMedication);
    }

    // ==========================================
    // Bulk Adjustment Calculations & Event Logic
    // ==========================================
    function switchBulkQuantile(quantile) {
        activeBulkQuantile = quantile;
        bulkMultiplier = 1.0;
        bulkSlider.value = 100;
        bulkSliderVal.innerText = "100%";
        
        updateBulkButtonUI();
        recalculateAndRenderTable();
    }

    function handleSliderChange(e) {
        const val = parseInt(e.target.value);
        bulkSliderVal.innerText = `${val}%`;
        bulkMultiplier = val / 100.0;
        
        recalculateAndRenderTable();
    }

    function updateBulkButtonUI() {
        btnBulkP10.classList.remove("active");
        btnBulkP50.classList.remove("active");
        btnBulkP90.classList.remove("active");
        
        if (activeBulkQuantile === "p10") btnBulkP10.classList.add("active");
        else if (activeBulkQuantile === "p50") btnBulkP50.classList.add("active");
        else if (activeBulkQuantile === "p90") btnBulkP90.classList.add("active");
    }

    /**
     * Re-runs the inventory calculation logic client-side based on:
     * - selected Quantile (p10, p50, p90)
     * - 30-day Buffer stock rule
     * - bulkMultiplier factor (slider)
     */
    function recalculateAndRenderTable() {
        if (!rawStateCache) return;
        
        actionPlanTableBody.innerHTML = "";
        const horizon = rawStateCache.forecast_days || 5;
        const facilities = ["HKM", "HKP"];
        const medications = ["Amlodipine", "Perindopril", "Simvastatin"];
        
        // 1. Calculate baseline targets and deficits for the active quantile
        const computedGrid = {
            "HKM": {},
            "HKP": {}
        };
        
        facilities.forEach(fac => {
            medications.forEach(med => {
                const facInfo = rawStateCache.medication_surge_district[fac][med];
                
                // Read expected daily doses based on active quantile
                let dailyDoses = facInfo.estimated_daily_doses_needed_p50;
                let surgeFactor = facInfo.surge_factor_p50;
                
                if (activeBulkQuantile === "p10") {
                    dailyDoses = facInfo.estimated_daily_doses_needed_p10;
                    surgeFactor = facInfo.surge_factor_p10;
                } else if (activeBulkQuantile === "p90") {
                    dailyDoses = facInfo.estimated_daily_doses_needed_p90;
                    surgeFactor = facInfo.surge_factor_p90;
                }
                
                const expectedDemand = dailyDoses * horizon;
                
                // 30 days buffer stock calculation
                let baseDaily = 3500; // HKM Amlodipine default
                if (fac === "HKM") {
                    baseDaily = med === "Amlodipine" ? 3500 : (med === "Perindopril" ? 2500 : 4000);
                } else {
                    baseDaily = med === "Amlodipine" ? 3000 : (med === "Perindopril" ? 2000 : 3500);
                }
                
                const bufferStock = baseDaily * 30;
                const requiredTarget = expectedDemand + bufferStock;
                
                const currentStock = originalAllocationData[fac][med].current_stock;
                const balance = currentStock - requiredTarget;
                
                computedGrid[fac][med] = {
                    current_stock: currentStock,
                    expected_demand: expectedDemand,
                    buffer_stock: bufferStock,
                    required_target: requiredTarget,
                    balance: balance,
                    deficit: Math.max(0.0, -balance),
                    relocation_qty: 0.0,
                    procurement_qty: 0.0,
                    lend_qty: 0.0
                };
            });
        });
        
        // 2. Perform relocation rules using active quantile balances
        medications.forEach(med => {
            const hkmItem = computedGrid["HKM"][med];
            const hkpItem = computedGrid["HKP"][med];
            
            // Relocate if one facility has surplus and the other has deficit
            if (hkmItem.balance < 0 && hkpItem.balance > 0) {
                const hkmDeficit = hkmItem.deficit;
                const hkpSurplus = hkpItem.balance;
                
                hkmItem.relocation_qty = Math.min(hkmDeficit, hkpSurplus);
                hkmItem.procurement_qty = Math.max(0.0, hkmDeficit - hkmItem.relocation_qty);
                hkpItem.lend_qty = hkmItem.relocation_qty;
                
            } else if (hkpItem.balance < 0 && hkmItem.balance > 0) {
                const hkpDeficit = hkpItem.deficit;
                const hkmSurplus = hkmItem.balance;
                
                hkpItem.relocation_qty = Math.min(hkpDeficit, hkmSurplus);
                hkpItem.procurement_qty = Math.max(0.0, hkpDeficit - hkpItem.relocation_qty);
                hkmItem.lend_qty = hkpItem.relocation_qty;
                
            } else {
                // If both are in deficit, both must procure
                if (hkmItem.balance < 0) hkmItem.procurement_qty = hkmItem.deficit;
                if (hkpItem.balance < 0) hkpItem.procurement_qty = hkpItem.deficit;
            }
        });
        
        // 3. Render Table rows applying the Bulk Adjustment Multiplier (slider)
        facilities.forEach(fac => {
            medications.forEach(med => {
                const item = computedGrid[fac][med];
                
                // Apply the bulk multiplier
                let finalReloc = item.relocation_qty * bulkMultiplier;
                let finalProc = item.procurement_qty * bulkMultiplier;
                
                // Fetch original baseline for modified CSS highlights
                const origReloc = originalAllocationData[fac][med].relocation_qty;
                const origProc = originalAllocationData[fac][med].procurement_qty;
                
                const isRelocModified = Math.abs(finalReloc - origReloc) > 0.01;
                const isProcModified = Math.abs(finalProc - origProc) > 0.01;
                
                let statusBadge = `<span style="color: var(--success-color); font-weight:600;">Safe</span>`;
                if (item.deficit > 0) {
                    statusBadge = `<span style="color: var(--danger-color); font-weight:600;">Deficit (${formatNumber(item.deficit)})</span>`;
                }
                
                // Formulate description message
                let msg = `${fac === "HKM" ? "Hospital Kuala Makar" : "Hospital Kampung Pisang"} stock is sufficient (Covers demand + buffer).`;
                if (item.deficit > 0) {
                    if (finalReloc > 0 && finalProc > 0) {
                        msg = `Deficit of ${formatNumber(item.deficit)} units. Relocating ${formatNumber(finalReloc)} and procuring ${formatNumber(finalProc)}.`;
                    } else if (finalReloc > 0) {
                        msg = `Deficit of ${formatNumber(item.deficit)} units will be fully covered by stock relocation.`;
                    } else {
                        msg = `Deficit of ${formatNumber(item.deficit)} units will be fully covered by emergency procurement.`;
                    }
                }
                
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td style="font-weight: 500;">${fac}</td>
                    <td>${med}</td>
                    <td>${formatNumber(item.current_stock)}</td>
                    <td>${formatNumber(item.expected_demand)}</td>
                    <td>
                        <input type="number" 
                               class="relocate-input ${isRelocModified ? 'modified' : ''}" 
                               data-facility="${fac}" 
                               data-medication="${med}" 
                               value="${finalReloc.toFixed(0)}" 
                               min="0" 
                               step="50">
                        <span class="cell-warning-badge hidden" id="warn-relocate-${fac}-${med}"></span>
                    </td>
                    <td>
                        <input type="number" 
                               class="procure-input ${isProcModified ? 'modified' : ''}" 
                               data-facility="${fac}" 
                               data-medication="${med}" 
                               value="${finalProc.toFixed(0)}" 
                               min="0" 
                               step="50">
                    </td>
                    <td>${statusBadge}</td>
                    <td class="status-msg-cell" style="font-size: 0.8rem; color: var(--text-secondary);">${msg}</td>
                `;
                
                actionPlanTableBody.appendChild(tr);
            });
        });
        
        // Add dynamic input listener to single cells
        document.querySelectorAll(".relocate-input, .procure-input").forEach(input => {
            input.addEventListener("input", (e) => {
                const el = e.target;
                const fac = el.dataset.facility;
                const med = el.dataset.medication;
                const val = parseFloat(el.value) || 0.0;
                
                const isRelocate = el.classList.contains("relocate-input");
                const origVal = isRelocate 
                    ? originalAllocationData[fac][med].relocation_qty 
                    : originalAllocationData[fac][med].procurement_qty;
                
                if (Math.abs(val - origVal) > 0.01) {
                    el.classList.add("modified");
                } else {
                    el.classList.remove("modified");
                }
                
                if (isRelocate) {
                    validateRelocation(el, fac, med, val);
                }
            });
        });
    }

    function validateRelocation(el, fac, med, val) {
        const donorFac = fac === "HKM" ? "HKP" : "HKM";
        const donorStock = originalAllocationData[donorFac][med].current_stock;
        const donorNeeded = originalAllocationData[donorFac][med].total_needed;
        const donorSurplus = Math.max(0, donorStock - donorNeeded);
        const warnEl = document.getElementById(`warn-relocate-${fac}-${med}`);
        
        if (val > donorSurplus) {
            warnEl.innerText = `Exceeds surplus in ${donorFac} (${formatNumber(donorSurplus)} max)`;
            toggleElement(warnEl, true);
            el.style.borderColor = "var(--danger-color)";
        } else {
            toggleElement(warnEl, false);
            el.style.borderColor = "";
        }
    }

    async function handleModifyRequest() {
        const feedback = modifyFeedbackInput.value.trim();
        if (!feedback) {
            alert("Please enter refinement guidelines.");
            return;
        }

        updateWorkflowStatus("running", "RE-ESTIMATING FORECAST...");
        btnSubmitModification.disabled = true;

        try {
            const res = await apiCall("/api/hitl", {
                session_id: currentSessionId,
                command: `/modify ${feedback}`
            });
            cacheAndLoadState(res);
            toggleElement(modificationFormContainer, false);
            modifyFeedbackInput.value = "";
        } catch (err) {
            alert("Refinement execution failed: " + err.message);
        } finally {
            btnSubmitModification.disabled = false;
            updateWorkflowStatus("idle", "IDLE");
        }
    }

    // ==========================================
    // Step 3 Approval & Dispatch
    // ==========================================
    async function handleApproveRequest() {
        let hasErrors = false;
        
        document.querySelectorAll(".relocate-input").forEach(input => {
            const fac = input.dataset.facility;
            const med = input.dataset.medication;
            const val = parseFloat(input.value) || 0.0;
            const donorFac = fac === "HKM" ? "HKP" : "HKM";
            const donorStock = originalAllocationData[donorFac][med].current_stock;
            const donorNeeded = originalAllocationData[donorFac][med].total_needed;
            const donorSurplus = Math.max(0, donorStock - donorNeeded);
            
            if (val > donorSurplus) {
                hasErrors = true;
            }
        });
        
        if (hasErrors) {
            alert("Cannot submit. Several relocation parameters exceed the source facility's available surplus stock.");
            return;
        }
        
        if (!confirm("Are you sure you want to sign off and dispatch this action plan?")) {
            return;
        }

        updateWorkflowStatus("running", "DISPATCHING PLANS...");
        btnApproveActionPlan.disabled = true;
        
        const overrides = {
            "HKM": {},
            "HKP": {}
        };
        
        let hasOverrides = false;
        
        document.querySelectorAll(".relocate-input, .procure-input").forEach(input => {
            const fac = input.dataset.facility;
            const med = input.dataset.medication;
            const val = parseFloat(input.value) || 0.0;
            const isRelocate = input.classList.contains("relocate-input");
            
            if (!overrides[fac][med]) {
                overrides[fac][med] = {};
            }
            
            if (isRelocate) {
                overrides[fac][med].relocation_qty = val;
                if (Math.abs(val - originalAllocationData[fac][med].relocation_qty) > 0.01) {
                    hasOverrides = true;
                }
            } else {
                overrides[fac][med].procurement_qty = val;
                if (Math.abs(val - originalAllocationData[fac][med].procurement_qty) > 0.01) {
                    hasOverrides = true;
                }
            }
        });
        
        const finalCommand = hasOverrides 
            ? `/approve ${JSON.stringify(overrides)}` 
            : "/approve";

        try {
            const res = await apiCall("/api/hitl", {
                session_id: currentSessionId,
                command: finalCommand
            });
            
            const state = res.state || {};
            
            if (state.post_safety_passed === "Fail") {
                alert("Post-Decision Compliance Audit Failed:\n" + state.post_safety_reason);
                cacheAndLoadState(res);
                return;
            }
            
            postSafetyReasonText.innerText = state.post_safety_reason || "All customized allocations verified.";
            
            dispatchHkmCard.innerHTML = `<h3>Hospital Kuala Makar (HKM) Message</h3>\n` + marked.parse(state.hkm_message || "");
            dispatchHkpCard.innerHTML = `<h3>Hospital Kampung Pisang (HKP) Message</h3>\n` + marked.parse(state.hkp_message || "");
            
            transitionToScreen(3);
        } catch (err) {
            alert("Plan dispatch execution failed: " + err.message);
        } finally {
            btnApproveActionPlan.disabled = false;
            updateWorkflowStatus("idle", "IDLE");
        }
    }

    function resetWizardState() {
        currentSessionId = null;
        alertTextInput.value = "";
        toggleElement(ingestionResultBox, false);
        toggleElement(btnProceedToAnalysis, false);
        toggleElement(modificationFormContainer, false);
        modifyFeedbackInput.value = "";
        
        transitionToScreen(1);
    }

    // ==========================================
    // Chart rendering (Daily Utilisation & Stock Projection)
    // ==========================================
    function renderCharts(facilityId, medName) {
        renderLineChart(facilityId, medName);
        renderBarChart(facilityId);
    }

    function renderLineChart(facilityId, medName) {
        const curvesData = rawStateCache.daily_demand_curves_district;
        if (!curvesData || !curvesData[facilityId] || !curvesData[facilityId][medName]) return;
        
        const dataSet = curvesData[facilityId][medName];
        
        const fontColor = currentTheme === "dark" ? "#FFFFFF" : "#1F2937";
        const gridColor = currentTheme === "dark" ? "rgba(255, 255, 255, 0.05)" : "rgba(0, 0, 0, 0.05)";
        
        const ctx = document.getElementById("remedi-line-chart").getContext("2d");
        
        if (lineChartInstance) {
            lineChartInstance.destroy();
        }
        
        lineChartInstance = new Chart(ctx, {
            type: "line",
            data: {
                labels: dataSet.dates,
                datasets: [
                    {
                        label: "Actual Utilisation",
                        data: dataSet.history,
                        borderColor: "#9CA3AF",
                        backgroundColor: "rgba(156, 163, 175, 0.1)",
                        borderWidth: 3,
                        tension: 0.1,
                        spanGaps: true
                    },
                    {
                        label: "TFT Forecast p10 (Conservative)",
                        data: dataSet.p10,
                        borderColor: "#F59E0B",
                        borderWidth: 2,
                        borderDash: [5, 5],
                        fill: false,
                        spanGaps: true
                    },
                    {
                        label: "TFT Forecast p50 (Expected)",
                        data: dataSet.p50,
                        borderColor: "#0EA5E9",
                        borderWidth: 2.5,
                        borderDash: [3, 3],
                        fill: false,
                        spanGaps: true
                    },
                    {
                        label: "TFT Forecast p90 (Extreme Surge)",
                        data: dataSet.p90,
                        borderColor: "#10B981",
                        borderWidth: 2,
                        borderDash: [5, 5],
                        fill: false,
                        spanGaps: true
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    x: {
                        grid: { color: gridColor },
                        ticks: { color: fontColor, font: { family: "Inter", size: 8 } }
                    },
                    y: {
                        grid: { color: gridColor },
                        ticks: { color: fontColor, font: { family: "Inter", size: 9 } }
                    }
                }
            }
        });
    }

    function renderBarChart(facilityId) {
        const meds = ["Amlodipine", "Perindopril", "Simvastatin"];
        const horizon = rawStateCache.forecast_days || 5;
        
        // 1. Current Stocks values
        const currentStocks = meds.map(med => originalAllocationData[facilityId][med].current_stock);
        
        // 2. Compute total requirements = expected forecast demand + 1 month buffer
        const getRequirement = (med, quantile) => {
            const facInfo = rawStateCache.medication_surge_district[facilityId][med];
            let daily = facInfo.estimated_daily_doses_needed_p50;
            if (quantile === "p10") daily = facInfo.estimated_daily_doses_needed_p10;
            else if (quantile === "p90") daily = facInfo.estimated_daily_doses_needed_p90;
            
            const expected = daily * horizon;
            
            // 30 days buffer
            let baseDaily = 3500;
            if (facilityId === "HKM") {
                baseDaily = med === "Amlodipine" ? 3500 : (med === "Perindopril" ? 2500 : 4000);
            } else {
                baseDaily = med === "Amlodipine" ? 3000 : (med === "Perindopril" ? 2000 : 3500);
            }
            const buffer = baseDaily * 30;
            return expected + buffer;
        };
        
        const p10Requirements = meds.map(med => getRequirement(med, "p10"));
        const p50Requirements = meds.map(med => getRequirement(med, "p50"));
        const p90Requirements = meds.map(med => getRequirement(med, "p90"));
        
        const fontColor = currentTheme === "dark" ? "#FFFFFF" : "#1F2937";
        const gridColor = currentTheme === "dark" ? "rgba(255, 255, 255, 0.05)" : "rgba(0, 0, 0, 0.05)";
        
        const ctx = document.getElementById("remedi-bar-chart").getContext("2d");
        
        if (barChartInstance) {
            barChartInstance.destroy();
        }
        
        barChartInstance = new Chart(ctx, {
            type: "bar",
            data: {
                labels: meds,
                datasets: [
                    {
                        label: "Current Stock",
                        data: currentStocks,
                        backgroundColor: "rgba(156, 163, 175, 0.6)",
                        borderColor: "#9CA3AF",
                        borderWidth: 1,
                        borderRadius: 4
                    },
                    {
                        label: "Req Target (p10)",
                        data: p10Requirements,
                        backgroundColor: "rgba(245, 158, 11, 0.6)",
                        borderColor: "#F59E0B",
                        borderWidth: 1,
                        borderRadius: 4
                    },
                    {
                        label: "Req Target (p50)",
                        data: p50Requirements,
                        backgroundColor: "rgba(14, 165, 233, 0.6)",
                        borderColor: "#0EA5E9",
                        borderWidth: 1,
                        borderRadius: 4
                    },
                    {
                        label: "Req Target (p90)",
                        data: p90Requirements,
                        backgroundColor: "rgba(16, 185, 129, 0.6)",
                        borderColor: "#10B981",
                        borderWidth: 1,
                        borderRadius: 4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    x: {
                        grid: { color: gridColor },
                        ticks: { color: fontColor, font: { family: "Inter" } }
                    },
                    y: {
                        grid: { color: gridColor },
                        ticks: { color: fontColor, font: { family: "Inter", size: 9 } }
                    }
                }
            }
        });
    }

    // ==========================================
    // Interactive Map Tile Layer updates
    // ==========================================
    function updateMapTileLayer(theme) {
        if (!remediMap) return;
        
        if (tileLayerInstance) {
            remediMap.removeLayer(tileLayerInstance);
        }
        
        const tileUrl = theme === "dark" 
            ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            : "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";
            
        tileLayerInstance = L.tileLayer(tileUrl, {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
            subdomains: 'abcd',
            maxZoom: 18
        }).addTo(remediMap);
    }

    function renderLogisticsMap(stockAllocation) {
        const coords = {
            hkm: [3.4500, 102.4000],
            hkp: [3.4800, 102.4300],
            mdho: [3.5300, 102.3500]
        };

        if (!remediMap) {
            remediMap = L.map("remedi-map").setView([3.4800, 102.4000], 11);
            updateMapTileLayer(currentTheme);
        } else {
            mapMarkers.forEach(m => remediMap.removeLayer(m));
            mapLines.forEach(l => remediMap.removeLayer(l));
            mapMarkers = [];
            mapLines = [];
        }

        const hkmPopup = `
            <div style="font-family: Inter; color: var(--text-primary);">
                <b style="color: var(--primary-color);">Hospital Kuala Makar (HKM)</b><br>
                <i>Main District Center</i><br><br>
                ${Object.keys(stockAllocation["HKM"]).map(med => {
                    const a = stockAllocation["HKM"][med];
                    return `• <b>${med}</b>: Stock ${formatNumber(a.current_stock)} (Deficit: <b>${formatNumber(a.deficit)}</b>)`;
                }).join("<br>")}
            </div>
        `;
        const hkmMarker = L.marker(coords.hkm).addTo(remediMap).bindPopup(hkmPopup);
        mapMarkers.push(hkmMarker);

        const hkpPopup = `
            <div style="font-family: Inter; color: var(--text-primary);">
                <b style="color: var(--success-color);">Hospital Kampung Pisang (HKP)</b><br>
                <i>District Clinic Partner</i><br><br>
                ${Object.keys(stockAllocation["HKP"]).map(med => {
                    const a = stockAllocation["HKP"][med];
                    return `• <b>${med}</b>: Stock ${formatNumber(a.current_stock)} (Deficit: <b>${formatNumber(a.deficit)}</b>)`;
                }).join("<br>")}
            </div>
        `;
        const hkpMarker = L.marker(coords.hkp).addTo(remediMap).bindPopup(hkpPopup);
        mapMarkers.push(hkpMarker);

        const mdhoPopup = `
            <div style="font-family: Inter; color: var(--text-primary);">
                <b style="color: var(--warning-color);">Makar District Health Office (MDHO)</b><br>
                <i>Central Logistics Depot</i><br><br>
                Central inventory buffers verified. Order endpoints active.
            </div>
        `;
        const mdhoMarker = L.marker(coords.mdho).addTo(remediMap).bindPopup(mdhoPopup);
        mapMarkers.push(mdhoMarker);

        let hkmToHkpLine = false;
        let hkpToHkmLine = false;
        let mdhoToHkmLine = false;
        let mdhoToHkpLine = false;
        
        Object.keys(stockAllocation["HKM"]).forEach(med => {
            const hkmItem = stockAllocation["HKM"][med];
            const hkpItem = stockAllocation["HKP"][med];
            
            if (hkmItem.relocation_qty > 0) hkpToHkmLine = true;
            if (hkmItem.lend_qty > 0) hkmToHkpLine = true;
            if (hkmItem.procurement_qty > 0) mdhoToHkmLine = true;
            
            if (hkpItem.relocation_qty > 0) hkmToHkpLine = true;
            if (hkpItem.lend_qty > 0) hkpToHkmLine = true;
            if (hkpItem.procurement_qty > 0) mdhoToHkpLine = true;
        });

        if (hkpToHkmLine) {
            const line = L.polyline([coords.hkp, coords.hkm], {
                color: "#10B981",
                dashArray: "6, 12",
                weight: 4,
                opacity: 0.8
            }).addTo(remediMap).bindPopup("<b>Relocation Route: HKP → HKM</b>");
            mapLines.push(line);
        }
        
        if (hkmToHkpLine) {
            const line = L.polyline([coords.hkm, coords.hkp], {
                color: "#F59E0B",
                dashArray: "6, 12",
                weight: 4,
                opacity: 0.8
            }).addTo(remediMap).bindPopup("<b>Relocation Route: HKM → HKP</b>");
            mapLines.push(line);
        }

        if (mdhoToHkmLine) {
            const line = L.polyline([coords.mdho, coords.hkm], {
                color: "#0EA5E9",
                weight: 3,
                opacity: 0.8
            }).addTo(remediMap).bindPopup("<b>Procurement Line: MDHO → HKM</b>");
            mapLines.push(line);
        }
        
        if (mdhoToHkpLine) {
            const line = L.polyline([coords.mdho, coords.hkp], {
                color: "#0EA5E9",
                weight: 3,
                opacity: 0.8
            }).addTo(remediMap).bindPopup("<b>Procurement Line: MDHO → HKP</b>");
            mapLines.push(line);
        }

        setTimeout(() => remediMap.invalidateSize(), 150);
    }

    // ==========================================
    // Helper Utilities
    // ==========================================
    function toggleElement(el, show) {
        if (show) {
            el.classList.remove("hidden");
        } else {
            el.classList.add("hidden");
        }
    }

    function updateWorkflowStatus(type, label) {
        workflowStatus.className = "status-indicator " + type;
        workflowStatus.innerText = label;
    }

    async function apiCall(endpoint, data = {}) {
        const response = await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            const errBody = await response.json();
            throw new Error(errBody.detail || "Server error");
        }
        return await response.json();
    }
});
