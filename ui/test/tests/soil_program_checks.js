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
		$("#programs, #addprogram, #soil-settings").remove();
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
		OSApp.SoilPrograms.settingsPage();
		$("#soil-groups").val("Critical\nNormal\nLow");
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
	it("does not remove a priority group while a program uses it", function () {
		OSApp.SoilPrograms.editPage(); header.rightBtn.on();
		OSApp.SoilPrograms.settingsPage(); $("#soil-groups").val("High"); header.rightBtn.on();
		assert.deepEqual(OSApp.SoilPrograms.load().groups, ["Normal"]);
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
});
