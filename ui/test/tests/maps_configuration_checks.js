/* eslint-disable */

describe("Optional deployment Maps configuration", function () {
	var sandbox, oldConfig;
	beforeEach(function () {
		sandbox = sinon.createSandbox();
		oldConfig = window.OSMapsConfig;
		window.OSMapsConfig = { apiKey: "" };
	});
	afterEach(function () {
		window.OSMapsConfig = oldConfig;
		sandbox.restore();
	});
	it("returns GPS coordinates without contacting Google when no key is configured", function () {
		var request = sandbox.stub($, "getJSON");
		var callback = sandbox.spy();
		OSApp.Options.coordsToLocation(12, 34, callback);
		assert.isTrue(callback.calledOnceWithExactly("12,34"));
		assert.isFalse(request.called);
	});
	it("preserves the supplied location fallback when Maps is disabled", function () {
		var callback = sandbox.spy();
		OSApp.Options.coordsToLocation(12, 34, callback, "Garden");
		assert.isTrue(callback.calledOnceWithExactly("Garden"));
	});
	it("does not open a map or request geolocation without a key", function () {
		var popup = sandbox.stub(OSApp.UIDom, "openPopup");
		var callback = sandbox.spy();
		OSApp.Options.overlayMap(callback);
		assert.isTrue(callback.calledOnceWithExactly(false));
		assert.isFalse(popup.called);
	});
	it("supports a deployment-supplied key and gracefully handles lookup failures", function () {
		window.OSMapsConfig = { apiKey: " example-browser-key " };
		var deferred = $.Deferred();
		var request = sandbox.stub($, "getJSON").returns(deferred.promise());
		var callback = sandbox.spy();
		OSApp.Options.coordsToLocation(12, 34, callback);
		assert.include(request.firstCall.args[0], "key=example-browser-key&");
		deferred.reject();
		assert.isTrue(callback.calledOnceWithExactly("12,34"));
	});
	it("accepts an absent or malformed deployment configuration as no Maps key", function () {
		window.OSMapsConfig = undefined;
		assert.equal(OSApp.Options.getMapsApiKey(), "");
		window.OSMapsConfig = { apiKey: 123 };
		assert.equal(OSApp.Options.getMapsApiKey(), "");
	});
});
