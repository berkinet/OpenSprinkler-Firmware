/* eslint-disable */

describe("Controller scheduling mode", function () {
	var controller, savedOptions, savedSettings, savedStations, sandbox, headerOptions;
	beforeEach(function () {
		controller = OSApp.currentSession.controller;
		savedOptions = controller.options;
		savedSettings = controller.settings;
		savedStations = controller.stations;
		controller.options = { fwv: 221, fwm: 5, hwv: 255, smode: 0 };
		controller.settings = { loc: "0,0", nbrd: 1, wto: {}, ps: [] };
		controller.stations = { snames: [], masop: [0], stn_dis: [0], stn_seq: [255] };
		sandbox = sinon.createSandbox();
		sandbox.stub(OSApp.UIDom, "changeHeader").callsFake(function (options) {
			headerOptions = options;
			return $("<button></button><button></button><button></button>");
		});
	});
	afterEach(function () {
		$("#os-options").remove();
		controller.options = savedOptions;
		controller.settings = savedSettings;
		controller.stations = savedStations;
		sandbox.restore();
	});
	it("places both selectable scheduling modes in their own section", function () {
		OSApp.Options.showOptions("scheduling");
		var section = $("#scheduling-options");
		assert.equal(section.length, 1);
		assert.include(section.text(), "Scheduling mode");
		assert.equal(section.find("#smode").val(), "0");
		assert.isFalse(section.find("option[value='0']").prop("disabled"));
		assert.isFalse(section.find("option[value='1']").prop("disabled"));
		assert.include(section.find("option[value='1']").text(), "editor preview");
		assert.notInclude(section.text(), "App Settings");
	});
	it("restores the controller-selected soil-water mode", function () {
		controller.options.smode = 1;
		OSApp.Options.showOptions("scheduling");
		assert.equal($("#smode").val(), "1");
	});
	it("offers Priority Groups only for the saved soil-water scheduling mode", function () {
		OSApp.Options.showOptions("scheduling");
		assert.lengthOf($("#priority-groups-link"), 0);
		controller.options.smode = 1;
		OSApp.Options.showOptions("scheduling");
		assert.equal($("#priority-groups-link").attr("href"), "#priority-groups");
		$("#smode").val("0").trigger("change");
		assert.equal($("#priority-groups-link").css("display"), "none");
	});
	it("does not offer this setting on firmware without the controller option", function () {
		delete controller.options.smode;
		OSApp.Options.showOptions();
		assert.equal($("#smode").length, 0);
		assert.equal($("#scheduling-options").length, 0);
	});
	it("saves the choice through the controller API, not local app storage", function () {
		OSApp.Options.showOptions();
		// Simulate refreshed controller state differing from the form to exercise saving.
		controller.options.smode = 1;
		var send = sandbox.stub(OSApp.Firmware, "sendToOS").returns($.Deferred().promise());
		var store = sandbox.spy(OSApp.Storage, "setItemSync");
		headerOptions.rightBtn.on();
		assert.isTrue(send.calledWithMatch(/\/co\?pw=&.*smode=0/));
		assert.isFalse(store.calledWith("smode"));
	});
	it("keeps manual location entry available without a deployment Maps key", function () {
		var oldConfig = window.OSMapsConfig;
		window.OSMapsConfig = { apiKey: "" };
		try {
			OSApp.Options.showOptions();
			var open = sandbox.stub(OSApp.UIDom, "openPopup");
			var map = sandbox.stub(OSApp.Options, "overlayMap");
			$("#loc").trigger("click");
			assert.isFalse(map.called);
			assert.isTrue(open.calledOnce);
			assert.equal(open.firstCall.args[0].find("#loc-entry").val(), "0,0");
		} finally {
			window.OSMapsConfig = oldConfig;
		}
	});
});
