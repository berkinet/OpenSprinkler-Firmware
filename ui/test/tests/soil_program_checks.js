/* eslint-disable */
describe("Soil-water program drafts", function () {
	var sandbox, oldController, oldIP, header, memory;
	beforeEach(function () {
		sandbox = sinon.createSandbox();
		oldController = OSApp.currentSession.controller;
		oldIP = OSApp.currentSession.ip;
		OSApp.currentSession.ip = "test-controller-A";
		OSApp.currentSession.controller = {
			options: { smode: 1, mas: 4 },
			stations: { snames: ["LT", "RM", "Disabled", "Master"], stn_dis: [4] }
		};
		memory = {};
		sandbox.stub(OSApp.Storage, "getItemSync").callsFake(key => memory[key] || null);
		sandbox.stub(OSApp.Storage, "setItemSync").callsFake((key, value) => { memory[key] = value; });
		sandbox.stub(OSApp.Bundles, "isLeader").returns(false);
		sandbox.stub(OSApp.Bundles, "getReferencingLeaders").returns([]);
		sandbox.stub(OSApp.UIDom, "changeHeader").callsFake(options => { header = options; return $(); });
		sandbox.stub(OSApp.UIDom, "changePage");
		sandbox.stub(OSApp.Errors, "showError");
		sandbox.stub(OSApp.Firmware, "sendToOS");
	});
	afterEach(function () {
		$("#programs, #addprogram, #soil-settings, #priority-groups, #preview, #soil-draft-export, #equipment-catalog").remove();
		OSApp.currentSession.controller = oldController;
		OSApp.currentSession.ip = oldIP;
		sandbox.restore();
	});
	it("saves and reopens one draft per valve without a controller program write", function () {
		OSApp.SoilPrograms.editPage();
		$("#soil-cycle, #soil-soak").val("60").trigger("input");
		assert.include($("#addprogram").text(), "Elapsed: 9 min");
		header.rightBtn.on();
		var draft = OSApp.SoilPrograms.load().programs[0];
		assert.equal(draft.sid, 0);
		assert.equal(draft.cycle, 1);
		assert.isFalse(OSApp.Firmware.sendToOS.called);
		OSApp.SoilPrograms.editPage();
		assert.equal($("#soil-zone option").length, 1);
		assert.equal($("#soil-zone").val(), "1");
		OSApp.SoilPrograms.editPage(0);
		assert.equal($("#soil-zone").val(), "0");
		assert.equal($("#soil-cycle").val(), "60");
	});
	it("uses the existing duration picker and converts its seconds to draft minutes", function () {
		var picker = sandbox.stub(OSApp.UIDom, "showDurationBox");
		OSApp.SoilPrograms.editPage();
		$("#soil-cycle").trigger("click");
		assert.equal(picker.lastCall.args[0].title, "Maximum ON per cycle");
		assert.isFalse(picker.lastCall.args[0].showSun);
		assert.equal($("#soil-cycle").val(), ""); // Opening/cancelling doesn't set a value.
		picker.lastCall.args[0].callback(30);
		$("#soil-soak").trigger("click");
		picker.lastCall.args[0].callback(60);
		assert.equal($("#soil-cycle").text(), "30s");
		assert.include($("#addprogram").text(), "Elapsed: 14 min");
		header.rightBtn.on();
		assert.equal(OSApp.SoilPrograms.load().programs[0].cycle, 0.5);
		assert.equal(OSApp.SoilPrograms.load().programs[0].soak, 1);
	});
	it("reopens existing minute-based drafts with the shared name and enable controls", function () {
		var data = OSApp.SoilPrograms.load();
		data.programs = [{sid: 0, name: '<img src=x onerror="bad()">', enabled: false, group: "Normal", cycle: 1, soak: 0, minimum: 0.5}];
		OSApp.SoilPrograms.save(data);
		OSApp.SoilPrograms.editPage(0);
		assert.equal($("#soil-cycle").val(), "60");
		assert.equal($("#soil-soak").text(), "0s");
		assert.equal($("#soil-minimum").val(), "30");
		assert.equal($("#soil-enabled").attr("type"), "checkbox");
		assert.isFalse($("#soil-enabled").prop("checked"));
		assert.lengthOf($("#addprogram img"), 0);
		assert.equal($("#soil-name").val(), data.programs[0].name);
		header.rightBtn.on();
		assert.isFalse(OSApp.SoilPrograms.load().programs[0].enabled);
		assert.equal(OSApp.SoilPrograms.load().programs[0].soak, 0);
	});
	it("isolates drafts between controllers", function () {
		var data = OSApp.SoilPrograms.load(); data.groups = ["A garden"];
		OSApp.SoilPrograms.save(data);
		OSApp.currentSession.ip = "test-controller-B";
		assert.deepEqual(OSApp.SoilPrograms.load().groups, ["Normal"]);
		OSApp.currentSession.ip = "test-controller-A";
		assert.deepEqual(OSApp.SoilPrograms.load().groups, ["A garden"]);
	});
	it("excludes disabled valves, masters and bundles", function () {
		OSApp.Bundles.isLeader.withArgs(1).returns(true);
		assert.deepEqual(OSApp.SoilPrograms.eligibleZones().map(z => z.sid), [0]);
	});
	it("does not accept a minimum pulse larger than the cycle", function () {
		OSApp.SoilPrograms.editPage();
		$("#soil-cycle").val(60); $("#soil-minimum").val(120);
		header.rightBtn.on();
		assert.equal(OSApp.SoilPrograms.load().programs.length, 0);
		assert.include(OSApp.Errors.showError.lastCall.args[0], "cannot exceed");
	});
	it("keeps independent drafts when editing another valve", function () {
		OSApp.SoilPrograms.editPage(); header.rightBtn.on();
		OSApp.SoilPrograms.editPage(); header.rightBtn.on();
		OSApp.SoilPrograms.editPage(0); $("#soil-name").val("Flowers"); header.rightBtn.on();
		var programs = OSApp.SoilPrograms.load().programs;
		assert.equal(programs.length, 2);
		assert.equal(programs.find(p => p.sid === 0).name, "Flowers");
		assert.equal(programs.find(p => p.sid === 1).name, "RM");
	});
	it("preserves shared window rules and ordered groups on save", function () {
		var initial = OSApp.SoilPrograms.load(); initial.groups = ["Critical", "Normal", "Low"];
		OSApp.SoilPrograms.save(initial);
		OSApp.SoilPrograms.settingsPage();
		$("#soil-settings button").filter(function () { return $(this).text() === "Add watering window"; }).trigger("click");
		$(".window-start").val("22:00"); $(".window-end").val("05:00");
		$("#window-day-0-0").prop("checked", true);
		$("#soil-excluded").val("2026-10-01");
		header.rightBtn.on();
		var data = OSApp.SoilPrograms.load();
		assert.deepEqual(data.groups, ["Critical", "Normal", "Low"]);
		assert.deepEqual(data.windows, [{ days: [0], start: "22:00", end: "05:00" }]);
		assert.equal(data.excluded, "2026-10-01");
		assert.isFalse(OSApp.Firmware.sendToOS.called);
	});
	it("rejects a window without weekdays and impossible exclusion dates", function () {
		OSApp.SoilPrograms.settingsPage();
		$("#soil-settings button").filter(function () { return $(this).text() === "Add watering window"; }).trigger("click");
		$(".window-start").val("06:00"); $(".window-end").val("07:00");
		header.rightBtn.on();
		assert.isFalse(OSApp.Storage.setItemSync.called);
		$("#window-day-0-0").prop("checked", true); $("#soil-excluded").val("2026-02-31");
		header.rightBtn.on();
		assert.isFalse(OSApp.Storage.setItemSync.called);
	});
	it("keeps used priority groups and at least one group", function () {
		OSApp.SoilPrograms.editPage(); header.rightBtn.on();
		OSApp.PriorityGroups.displayPage();
		assert.isTrue($(".priority-remove").prop("disabled"));
		assert.throws(() => OSApp.PriorityGroups.save(["Normal"], [{original: null, name: "High"}]), "Reassign programs");
		assert.throws(() => OSApp.PriorityGroups.save(["Normal"], []), "at least one group");
		assert.deepEqual(OSApp.SoilPrograms.load().groups, ["Normal"]);
	});
	it("adds and reorders named groups and refreshes program choices", function () {
		OSApp.PriorityGroups.displayPage();
		$("#add-priority-group").trigger("click");
		$(".priority-group-name").last().val("Critical").trigger("input");
		$(".priority-up").last().trigger("click");
		assert.isTrue($(".priority-up").first().prop("disabled"));
		assert.isTrue($(".priority-down").last().prop("disabled"));
		header.rightBtn.on();
		assert.deepEqual(OSApp.SoilPrograms.load().groups, ["Critical", "Normal"]);
		OSApp.SoilPrograms.editPage();
		assert.deepEqual($("#soil-group option").map(function() { return this.value; }).get(), ["Critical", "Normal"]);
		assert.isFalse(OSApp.Firmware.sendToOS.called);
	});
	it("renames used groups atomically, including swapped names", function () {
		var data = OSApp.SoilPrograms.load(); data.groups = ["High", "Low"];
		data.programs = [{sid: 0, group: "High"}, {sid: 1, group: "Low"}];
		OSApp.SoilPrograms.save(data);
		OSApp.PriorityGroups.save(data.groups, [{original: "Low", name: "High"}, {original: "High", name: "Low"}]);
		assert.deepEqual(OSApp.SoilPrograms.load().programs.map(p => p.group), ["Low", "High"]);
	});
	it("rejects empty or duplicate group names without changing assignments", function () {
		for (const rows of [[{original:"Normal",name:" "}], [{original:"Normal",name:"High"},{original:null,name:" high "}]]) {
			assert.throws(() => OSApp.PriorityGroups.save(["Normal"], rows));
		}
		assert.deepEqual(OSApp.SoilPrograms.load().groups, ["Normal"]);
	});
	it("rejects stale group edits and keeps unrelated new draft changes", function () {
		var latest = OSApp.SoilPrograms.load(); latest.excluded = "2026-10-01";
		OSApp.SoilPrograms.save(latest);
		OSApp.PriorityGroups.save(["Normal"], [{original:"Normal",name:"Garden"}]);
		assert.equal(OSApp.SoilPrograms.load().excluded, "2026-10-01");
		assert.throws(() => OSApp.PriorityGroups.save(["Normal"], [{original:"Normal",name:"Old"}]), "another window");
	});
	it("shared settings cannot overwrite renamed or reordered groups", function () {
		OSApp.SoilPrograms.settingsPage();
		OSApp.PriorityGroups.save(["Normal"], [{original:"Normal",name:"Garden"}]);
		header.rightBtn.on();
		assert.deepEqual(OSApp.SoilPrograms.load().groups, ["Garden"]);
	});
	it("does not render group editing controls in Standard mode", function () {
		OSApp.currentSession.controller.options.smode = 0;
		OSApp.PriorityGroups.displayPage();
		assert.lengthOf($("#add-priority-group, .priority-group-name"), 0);
	});
	it("keeps an unreadable draft intact instead of overwriting it", function () {
		memory[OSApp.SoilPrograms.storageKey()] = "invalid-json";
		assert.throws(() => OSApp.SoilPrograms.load());
		assert.isFalse(OSApp.Storage.setItemSync.called);
	});
	it("counts soak only between pulses and supports a shorter final pulse", function () {
		assert.include(OSApp.SoilPrograms.pulseSummary(5, 1, 1), "Elapsed: 9 min");
		assert.include(OSApp.SoilPrograms.pulseSummary(5, 2, 1), "2 × 2 min + 1 min");
		assert.include(OSApp.SoilPrograms.pulseSummary(5, 10, 1), "Elapsed: 5 min");
	});
	it("produces the exact draft fixture consumed by the offline scheduling engine", function () {
		var expected = JSON.parse(JSON.stringify(window.__karma__.config.engineDraftFixture));
		var initial = OSApp.SoilPrograms.load(); initial.groups = expected.groups.slice();
		OSApp.SoilPrograms.save(initial);
		OSApp.SoilPrograms.settingsPage();
		expected.windows.forEach(function (rule, i) {
			$("#soil-settings button").filter(function () { return $(this).text() === "Add watering window"; }).trigger("click");
			$("#window-start-"+i).val(rule.start); $("#window-end-"+i).val(rule.end);
			rule.days.forEach(day => $("#window-day-"+i+"-"+day).prop("checked", true));
		});
		Object.keys(expected.profile).forEach(key => $("#profile-"+key).val(expected.profile[key]));
		$("#soil-shortage").val(expected.shortage); $("#soil-excluded").val(expected.excluded);
		header.rightBtn.on();
		expected.programs.forEach(function (p) {
			OSApp.SoilPrograms.editPage();
			$("#soil-zone").val(p.sid); $("#soil-name").val(p.name); $("#soil-group").val(p.group);
			$("#soil-enabled").prop("checked", p.enabled);
			$("#soil-amount-mode").val(p.amountMode).trigger("change"); $("#soil-depth").val(p.depth);
			["rate", "efficiency"].forEach(key => $("#soil-"+key).val(p[key]));
			["cycle", "soak", "minimum", "runtime"].forEach(key => $("#soil-"+key).val(p[key] === "" ? "" : Math.round(p[key]*60)));
			header.rightBtn.on();
		});
		assert.deepEqual(JSON.parse(OSApp.SoilPrograms.exportDraft()), expected);
		assert.isFalse(OSApp.Firmware.sendToOS.called);
	});
	it("accepts zero crop and effective-rain factors while rejecting zero storage", function () {
		OSApp.SoilPrograms.settingsPage();
		$("#profile-crop, #profile-rain").val(0);
		header.rightBtn.on();
		assert.strictEqual(OSApp.SoilPrograms.load().profile.crop, 0);
		assert.strictEqual(OSApp.SoilPrograms.load().profile.rain, 0);
		$("#profile-capacity").val(0);
		OSApp.Storage.setItemSync.resetHistory();
		header.rightBtn.on();
		assert.isFalse(OSApp.Storage.setItemSync.called);
	});
	it("exports only the saved draft, including uncalibrated blanks", function () {
		OSApp.SoilPrograms.editPage(); header.rightBtn.on();
		var saved = OSApp.SoilPrograms.load();
		OSApp.SoilPrograms.editPage(0); $("#soil-name").val("Unsaved name");
		assert.deepEqual(JSON.parse(OSApp.SoilPrograms.exportDraft()), saved);
		assert.strictEqual(JSON.parse(OSApp.SoilPrograms.exportDraft()).programs[0].rate, "");
		sandbox.stub(OSApp.UIDom, "openPopup").callsFake(popup => $("body").append(popup));
		OSApp.SoilPrograms.previewPage();
		$("#export-soil-draft").trigger("click");
		assert.equal($("#download-soil-draft").attr("download"), "soil-water-draft.json");
		assert.isTrue($("#soil-draft-json").prop("readonly"));
		assert.deepEqual(JSON.parse($("#soil-draft-json").val()), saved);
		assert.deepEqual(JSON.parse(decodeURIComponent($("#download-soil-draft").attr("href").split(",")[1])), saved);
		assert.isFalse(OSApp.Firmware.sendToOS.called);
	});
	it("saves fixed runtime and reopens it without requiring delivery calibration", function () {
		OSApp.SoilPrograms.editPage();
		$("#soil-runtime").val(300).trigger("change");
		$("#soil-cycle, #soil-soak").val(60).trigger("change");
		$("#soil-minimum").val(30);
		header.rightBtn.on();
		var saved = JSON.parse(OSApp.SoilPrograms.exportDraft());
		assert.equal(saved.version, 2);
		assert.equal(saved.programs[0].amountMode, "runtime");
		assert.equal(saved.programs[0].runtime, 5);
		assert.equal(saved.programs[0].rate, "");
		OSApp.SoilPrograms.editPage(0);
		assert.equal($("#soil-runtime").val(), "300");
		assert.include($("#addprogram").text(), "Elapsed: 9 min");
		assert.isFalse(OSApp.Firmware.sendToOS.called);
	});
	it("previews catalogue geometry and only applies it explicitly", function () {
		OSApp.SoilPrograms.editPage();
		$("#soil-amount-mode").val("depth").trigger("change");
		$("#equipment-choice").val("jardibric-a1480").trigger("change");
		$("#equipment-rows").val(.5).trigger("input");
		assert.equal($("#soil-rate").val(), "");
		$("#apply-equipment").trigger("click");
		assert.closeTo(Number($("#soil-rate").val()), 12.121212, .00001);
		assert.equal($("#soil-efficiency").val(), "");
		$("#soil-calibration-source").val("catalogue").trigger("change"); $("#soil-depth").val(6);
		header.rightBtn.on();
		var saved = OSApp.SoilPrograms.load().programs[0];
		assert.closeTo(saved.rate, 12.121212, .00001); assert.equal(saved.depth, 6);
		assert.equal(JSON.parse(saved.equipment).entry.id, "jardibric-a1480");
		var base = OSApp.EquipmentCatalog.load(), next = JSON.parse(JSON.stringify(base));
		next.entries = [];
		OSApp.EquipmentCatalog.save(base, next);
		OSApp.SoilPrograms.editPage(0);
		assert.closeTo(Number($("#soil-rate").val()), 12.121212, .00001);
		assert.include($("#addprogram").text(), "Jardibric Aqua Gout");
	});
	it("maintains catalogue entries and safely backs up and imports them", function () {
		sandbox.stub(OSApp.UIDom, "areYouSure").callsFake((title, message, callback) => callback());
		OSApp.EquipmentCatalog.displayPage();
		$("#add-equipment").trigger("click");
		$("#catalog-name").val("Test hose"); $("#catalog-type").val("hose").trigger("change");
		$("#catalog-flow").val(12); $("#catalog-conditions").val("At 1 bar");
		$("#save-equipment").trigger("click");
		assert.equal(OSApp.EquipmentCatalog.load().entries.at(-1).flow, 12);
		$(".catalog-entry").last().trigger("click");
		$("#catalog-flow").val(10); $("#save-equipment").trigger("click");
		$("#export-catalog").trigger("click");
		var exported = $("#catalog-json").val();
		assert.equal(JSON.parse(exported).entries.at(-1).flow, 10);
		$(".catalog-entry").last().trigger("click"); $("#delete-equipment").trigger("click");
		assert.isFalse(OSApp.EquipmentCatalog.load().entries.some(e => e.name === "Test hose"));
		$("#catalog-json").val(exported); $("#import-catalog").trigger("click");
		assert.equal(OSApp.EquipmentCatalog.load().entries.at(-1).flow, 10);
		assert.isFalse(OSApp.Firmware.sendToOS.called);
	});
	it("rejects invalid catalogue data, stale saves, and unsafe layout numbers", function () {
		var base = OSApp.EquipmentCatalog.load(), next = JSON.parse(JSON.stringify(base));
		next.entries[0].efficiency = 101;
		assert.throws(() => OSApp.EquipmentCatalog.save(base, next));
		next.entries[0].efficiency = 85; next.entries[0].name = "Changed";
		OSApp.EquipmentCatalog.save(base, next);
		assert.throws(() => OSApp.EquipmentCatalog.save(base, base), "another window");
		assert.throws(() => OSApp.EquipmentCatalog.calculate(base.entries[0], {rows: 0}));
		var emitter = {id:"e",name:"Emitter",type:"emitter",flow:2,spacing:"",efficiency:"",source:"",conditions:""};
		assert.equal(OSApp.EquipmentCatalog.calculate(emitter, {count:20,area:10}), 4);
		assert.throws(() => OSApp.EquipmentCatalog.calculate(emitter, {count:1.5,area:10}));
		emitter.type = "hose"; emitter.flow = 12;
		assert.equal(OSApp.EquipmentCatalog.calculate(emitter, {length:25,area:30}), 10);
		memory[OSApp.EquipmentCatalog.key] = "invalid";
		assert.throws(() => OSApp.EquipmentCatalog.load());
	});
	it("does not render catalogue controls in Standard mode or interpret names as markup", function () {
		OSApp.currentSession.controller.options.smode = 0;
		OSApp.EquipmentCatalog.displayPage();
		assert.lengthOf($("#add-equipment"), 0);
		OSApp.currentSession.controller.options.smode = 1;
		var base = OSApp.EquipmentCatalog.load(), next = JSON.parse(JSON.stringify(base));
		next.entries[0].name = '<img src=x onerror="bad()">';
		OSApp.EquipmentCatalog.save(base, next);
		OSApp.EquipmentCatalog.displayPage();
		assert.lengthOf($("#equipment-catalog img"), 0);
	});

	it("shows manual calibration or catalogue controls exclusively and preserves the saved choice", function () {
		OSApp.SoilPrograms.editPage();
		$("#soil-amount-mode").val("depth").trigger("change");
		assert.notEqual($("#soil-manual-calibration").css("display"), "none");
		assert.equal($("#soil-catalogue-calibration").css("display"), "none");
		$("#soil-calibration-source").val("catalogue").trigger("change");
		assert.equal($("#soil-manual-calibration").css("display"), "none");
		assert.notEqual($("#soil-catalogue-calibration").css("display"), "none");
		$("#equipment-choice").val("jardibric-a1480").trigger("change");
		$("#equipment-rows").val(.5).trigger("input");
		assert.include($("#equipment-rows").closest(".ui-field-contain").find("button").attr("title"), "raspberries");
		header.rightBtn.on();
		assert.include(OSApp.Errors.showError.lastCall.args[0], "Apply");
		$("#apply-equipment").trigger("click"); header.rightBtn.on();
		OSApp.SoilPrograms.editPage(0);
		assert.equal($("#soil-calibration-source").val(), "catalogue");
		assert.equal($("#equipment-rows").val(), "0.5");
		assert.equal($("#soil-manual-calibration").css("display"), "none");
		$("#equipment-rows").val(1).trigger("input");
		header.rightBtn.on();
		assert.include(OSApp.Errors.showError.lastCall.args[0], "Apply");
		$("#soil-calibration-source").val("manual").trigger("change");
		$("#soil-rate").val(10); $("#soil-efficiency").val(85); header.rightBtn.on();
		assert.equal(OSApp.SoilPrograms.load().programs[0].calibrationSource, "manual");
		assert.notProperty(OSApp.SoilPrograms.load().programs[0], "equipment");
	});

});
