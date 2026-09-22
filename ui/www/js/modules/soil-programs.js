/* global $ */
/* OpenSprinkler App \u2014 AGPL-3.0; see ui/LICENSE. */
var OSApp = OSApp || {};
OSApp.SoilPrograms = OSApp.SoilPrograms || {};

// Drafts deliberately use a separate, controller-scoped schema. They never
// enter /cp or the legacy program array. Controller persistence comes later.
OSApp.SoilPrograms.storageKey = function() {
	return "soilProgramDraft:v1:" + encodeURIComponent( OSApp.currentSession.token || OSApp.currentSession.ip || window.location.host );
};
OSApp.SoilPrograms.load = function() {
	var raw = OSApp.Storage.getItemSync( OSApp.SoilPrograms.storageKey() );
	if ( raw ) {
		var data = JSON.parse( raw );
		if ( ![ 1, 2 ].includes( data.version ) || !Array.isArray( data.programs ) || !Array.isArray( data.groups ) ) {
			throw new Error( "Unsupported soil-water draft. Stored data has not been changed." );
		}
		return data;
	}
	return { version: 1, programs: [], groups: [ "Normal" ], windows: [], excluded: "", shortage: "report_only", profile: {} };
};
OSApp.SoilPrograms.save = function( data ) {
	OSApp.Storage.setItemSync( OSApp.SoilPrograms.storageKey(), JSON.stringify( data ) );
};
OSApp.SoilPrograms.eligibleZones = function() {
	var c = OSApp.currentSession.controller;
	return ( c.stations.snames || [] ).map( function( name, sid ) {
		return { sid: sid, name: name };
	} ).filter( function( zone ) {
		return !( ( c.stations.stn_dis || [] )[ zone.sid >> 3 ] & ( 1 << ( zone.sid % 8 ) ) ) &&
			![ c.options.mas, c.options.mas2, c.options.mas3, c.options.mas4 ].includes( zone.sid + 1 ) &&
			!OSApp.Bundles.isLeader( zone.sid ) && OSApp.Bundles.getReferencingLeaders( zone.sid ).length === 0;
	} );
};
OSApp.SoilPrograms.pulseSummary = function( total, cycle, soak ) {
	if ( !( total > 0 && cycle > 0 && soak >= 0 ) || ![ total, cycle, soak ].every( Number.isFinite ) ) {
		return "Enter a total ON time and cycle settings to preview the timing.";
	}
	var count = Math.ceil( total / cycle ), last = total - ( count - 1 ) * cycle;
	return count + " pulse" + ( count === 1 ? "" : "s" ) + ": " +
		( count > 1 ? ( count - 1 ) + " \xd7 " + cycle + " min + " : "" ) + last.toFixed( 2 ).replace( /\.?0+$/, "" ) +
		" min. Total ON: " + total + " min. Elapsed: " + Math.round( ( total + ( count - 1 ) * soak ) * 100 ) / 100 +
		" min, including soak between pulses. No final soak.";
};
OSApp.SoilPrograms.page = function( id, title, back, save, rightButton ) {
	var page = $( "<div data-role='page'><main class='ui-content'></main></div>" ).attr( "id", id );
	if ( id !== "programs" ) {
		page.find( "main" ).css( { "max-width": "760px", margin: "0 auto" } ).append(
			$( "<div role='note'></div>" ).css( { padding: "12px 16px", background: "#fff2d6", color: "#493714", "border-left": "4px solid #c3841c", "border-radius": "5px", "margin-bottom": "20px" } ).append(
				$( "<strong></strong>" ).text( "Soil water balance \xb7 editor preview" ),
				$( "<p></p>" ).css( "margin-bottom", 0 ).text( "Automatic watering is paused in this mode. Save draft stores these forms in this browser for this controller; the engine and controller storage are not connected yet." )
			)
		);
	}
	var header = { title: title, leftBtn: { icon: "carat-l", text: "Back", on: function() { if ( typeof back === "function" ) { back(); } else { OSApp.UIDom.changePage( back ); } } } };
	if ( save ) { header.rightBtn = { icon: "check", text: "Save draft", on: save }; }
	if ( rightButton ) { header.rightBtn = rightButton; }
	OSApp.UIDom.changeHeader( header );
	page.one( "pagehide", function() { page.remove(); } );
	$( "#" + id ).remove();
	$.mobile.pageContainer.append( page );
	return page;
};
OSApp.SoilPrograms.field = function( parent, id, label, value, type, hint ) {
	var row = $( "<div class='ui-field-contain'></div>" ).appendTo( parent );
	$( "<label></label>" ).attr( "for", id ).text( label ).appendTo( row );
	var input = $( "<input data-mini='true'>" ).attr( { id: id, type: type || "text" } ).val( value === undefined ? "" : value ).appendTo( row );
	if ( type === "number" ) { input.attr( { min: 0, step: "any" } ); }
	if ( hint ) { $( "<p class='small'></p>" ).text( hint ).appendTo( row ); }
	return input;
};
// Both draft versions store minutes; shared UI controls use seconds.
OSApp.SoilPrograms.durationField = function( parent, id, label, minutes ) {
	var row = $( "<div class='ui-field-contain duration-input'></div>" ).appendTo( parent ),
		seconds = minutes === "" || minutes === undefined ? "" : Math.round( minutes * 60 );
	$( "<label></label>" ).attr( "for", id ).text( label ).appendTo( row );
	var button = $( "<button type='button' data-mini='true' class='pad_buttons'></button>" ).attr( "id", id ).val( seconds )
		.text( seconds === "" ? OSApp.Language._( "Not set" ) : OSApp.Dates.dhms2str( OSApp.Dates.sec2dhms( seconds ) ) ).appendTo( row );
	OSApp.UIDom.bindDurationButton( button, { title: label, preventCompression: true, showSun: false } );
	return button;
};
OSApp.SoilPrograms.durationMinutes = function( button ) {
	return button.val() === "" ? "" : Number( button.val() ) / 60;
};
OSApp.SoilPrograms.select = function( parent, id, label, items, value ) {
	var row = $( "<div class='ui-field-contain'></div>" ).appendTo( parent );
	$( "<label></label>" ).attr( "for", id ).text( label ).appendTo( row );
	var select = $( "<select data-mini='true'></select>" ).attr( "id", id ).appendTo( row );
	items.forEach( function( item ) { $( "<option></option>" ).val( item.value ).text( item.label ).appendTo( select ); } );
	if ( value !== undefined ) { select.val( String( value ) ); }
	return select;
};
// Shared daily-hours control; site legal windows always remain authoritative.
OSApp.SoilPrograms.hoursSummary = function( value ) {
	return value && value.mode === "custom" ? value.start + " - " + value.end : "Any time within legal watering windows";
};
OSApp.SoilPrograms.hoursControl = function( parent, id, value, inherited ) {
	value = value || { mode: inherited === undefined ? "all" : "inherit" };
	var choices = [ { value: "all", label: "Any time within legal watering windows" }, { value: "custom", label: "Set permitted hours" } ];
	if ( inherited !== undefined ) { choices.unshift( { value: "inherit", label: "Use default: " + OSApp.SoilPrograms.hoursSummary( inherited ) } ); }
	var mode = OSApp.SoilPrograms.select( parent, id + "-mode", "Permitted hours", choices, value.mode ),
		box = $( "<div></div>" ).appendTo( parent ),
		start = OSApp.SoilPrograms.field( box, id + "-start", "From", value.start, "time" ),
		end = OSApp.SoilPrograms.field( box, id + "-end", "Until", value.end, "time" );
	parent.append( "<p class='small'>Controller local time, every day. An end before the start crosses midnight. All watering pulses must finish within permitted hours and site legal windows; excluded dates still apply.</p>" );
	function visibility() { box.toggle( mode.val() === "custom" ); }
	mode.on( "change", visibility ); visibility();
	return function() {
		var result = { mode: mode.val() };
		if ( result.mode === "custom" ) {
			result.start = start.val(); result.end = end.val();
			if ( ![ result.start, result.end ].every( function( t ) { return /^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/.test( t ); } ) || result.start === result.end ) {
				throw new Error( "Enter distinct permitted start and end times, or select Any time." );
			}
		}
		return result;
	};
};
OSApp.SoilPrograms.defaultHoursControl = function( parent ) {
	var data;
	try { data = OSApp.SoilPrograms.load(); } catch ( e ) { parent.append( $( "<p></p>" ).text( e.message ) ); return; }
	parent.append( "<h3>Default permitted hours</h3><p class='small'>Programs using the default follow later changes automatically. Saved as a browser-local draft.</p>" );
	var read = OSApp.SoilPrograms.hoursControl( parent, "soil-default-hours", data.defaultHours ), status = $( "<p role='status'></p>" );
	parent.append( $( "<button type='button' class='ui-btn ui-mini noselect'>Save default hours draft</button>" ).on( "click", function() {
		try {
			var hours = read(), latest = OSApp.SoilPrograms.load();
			latest.version = 2; latest.defaultHours = hours; OSApp.SoilPrograms.save( latest );
			status.text( "Default permitted hours saved." );
		} catch ( e ) { OSApp.Errors.showError( e.message ); }
	} ), status );
	parent.find( ":input" ).addClass( "noselect" );
};
OSApp.SoilPrograms.displayPage = function() {
	var page = OSApp.SoilPrograms.page( "programs", OSApp.Language._( "Programs" ), "#sprinklers", null, {
		icon: "plus",
		text: OSApp.Language._( "Add" ),
		on: function() { OSApp.UIDom.changePage( "#addprogram" ); }
	} ), body = page.find( "main" ), data;
	try { data = OSApp.SoilPrograms.load(); } catch ( e ) { body.append( $( "<p></p>" ).text( e.message ) ); return; }
	if ( !data.programs.length ) {
		body.append( $( "<p class='center'></p>" ).text( OSApp.Language._( "You have no programs currently added. Tap the Add button on the top right corner to get started." ) ) );
	} else {
		body.append( $( "<p class='center'></p>" ).text( OSApp.Language._( "Click any program below to edit. Be sure to save changes." ) ),
			$( "<p class='center'></p>" ).text( OSApp.Language._( "Number of Programs" ) + ": " + data.programs.length ) );
	}
	data.programs.forEach( function( program ) {
		var name = OSApp.currentSession.controller.stations.snames[ program.sid ] || "Unavailable valve";
		var button = $( "<a href='#' class='ui-btn ui-corner-all'></a>" ).css( { "text-align": "left", "white-space": "normal" } ).text( program.name );
		button.append( $( "<div class='small'></div>" ).text( name + " \xb7 " + program.group + " \xb7 Garden profile \xb7 " + ( program.enabled ? "Enabled draft" : "Disabled draft" ) ) );
		button.on( "click", function() { OSApp.UIDom.changePage( "#addprogram", { soilZone: program.sid } ); return false; } );
		body.append( button );
	} );
};
OSApp.SoilPrograms.editPage = function( sid ) {
	var page, data, program, fields = {}, originalSid = sid, equipmentSnapshot, readHours;
	function save() {
		if ( !data || !fields.zone ) { return; }
		try { data = OSApp.SoilPrograms.load(); } catch ( e ) { return OSApp.Errors.showError( e.message ); }
		if ( !data.groups.includes( fields.group.val() ) ) { return OSApp.Errors.showError( "Priority groups changed. Reopen this program to select a current group." ); }
		var chosen = Number( fields.zone.val() );
		if ( fields.zone.val() === null || !OSApp.SoilPrograms.eligibleZones().some( function( z ) { return z.sid === chosen; } ) ) {
			return OSApp.Errors.showError( "Choose an available valve." );
		}
		if ( data.programs.some( function( p ) { return p.sid === chosen && p.sid !== originalSid; } ) ) {
			return OSApp.Errors.showError( "This valve already has a soil-water program." );
		}
		if ( !fields.name.val().trim() ) { return OSApp.Errors.showError( "Enter a program name." ); }
		var equipment;
		try { equipment = fields.amountMode.val() !== "runtime" && fields.calibrationSource.val() === "catalogue" ? equipmentSnapshot() : undefined; } catch ( e ) { return OSApp.Errors.showError( e.message ); }
		var result = { calibrationSource: fields.calibrationSource.val(), sid: chosen, name: fields.name.val().trim(), profile: "garden", group: fields.group.val(), enabled: fields.enabled.prop( "checked" ) };
		try { result.permittedHours = readHours(); } catch ( e ) { return OSApp.Errors.showError( e.message ); }
		result.amountMode = fields.amountMode.val();
		for ( var key of [ "rate", "efficiency", "cycle", "soak", "minimum", "runtime", "depth" ] ) {
			var raw = [ "cycle", "soak", "minimum", "runtime" ].includes( key ) ? OSApp.SoilPrograms.durationMinutes( fields[ key ] ) : fields[ key ].val(), number = Number( raw );
			if ( raw === "" ) { result[ key ] = ""; continue; }
			if ( !Number.isFinite( number ) || number < 0 || ( key !== "soak" && number === 0 ) || ( key === "efficiency" && number > 100 ) ) {
				return OSApp.Errors.showError( "Enter positive values; efficiency must be 1\u2013100%. Soak may be zero." );
			}
			result[ key ] = number;
		}
		if ( result.minimum !== "" && result.cycle !== "" && result.minimum > result.cycle ) {
			return OSApp.Errors.showError( "Minimum useful pulse cannot exceed the maximum cycle." );
		}
		if ( result.amountMode === "runtime" && result.runtime !== "" && result.minimum !== "" && result.runtime < result.minimum ) {
			return OSApp.Errors.showError( "Runtime per watering cannot be shorter than the minimum useful pulse." );
		}
		if ( equipment ) { result.equipment = equipment; }
		data.version = 2;
		data.programs = data.programs.filter( function( p ) { return p.sid !== originalSid; } ).concat( [ result ] );
		try { OSApp.SoilPrograms.save( data ); } catch ( e ) { return OSApp.Errors.showError( "Could not save draft: " + e.message ); }
		OSApp.UIDom.changePage( "#programs" );
	}
	page = OSApp.SoilPrograms.page( "addprogram", sid === undefined ? "Add soil-water program" : "Edit soil-water program", "#programs", save );
	var body = page.find( "main" );
	try { data = OSApp.SoilPrograms.load(); } catch ( e ) { body.append( $( "<p></p>" ).text( e.message ) ); return; }
	program = data.programs.find( function( p ) { return p.sid === sid; } ) || { enabled: true, group: data.groups[ 0 ] };
	var zones = OSApp.SoilPrograms.eligibleZones().filter( function( zone ) {
		return zone.sid === sid || !data.programs.some( function( p ) { return p.sid === zone.sid; } );
	} );
	if ( !zones.length ) { body.append( $( "<p></p>" ).text( "Every available valve already has a program, or no individual valves are enabled. Enable a valve in station settings or edit an existing draft." ) ); return; }
	body.append( "<h2>Valve & priority</h2>" );
	fields.zone = OSApp.SoilPrograms.select( body, "soil-zone", "Zone / valve", zones.map( function( z ) { return { value: z.sid, label: z.name }; } ), program.sid );
	body.append( OSApp.Programs.makeNameField( "soil-name", program.name || zones[ 0 ].name ),
		OSApp.Programs.makeEnabledField( "soil-enabled", program.enabled ) );
	fields.name = body.find( "#soil-name" );
	fields.enabled = body.find( "#soil-enabled" );
	OSApp.SoilPrograms.select( body, "soil-profile", "Site profile", [ { value: "garden", label: "Garden (shared)" } ], "garden" );
	fields.group = OSApp.SoilPrograms.select( body, "soil-group", "Priority group", data.groups.map( function( g ) { return { value: g, label: g }; } ), program.group );
	body.append( "<h2>Permitted watering hours</h2>" );
	readHours = OSApp.SoilPrograms.hoursControl( $( "<div></div>" ).appendTo( body ), "soil-hours", program.permittedHours, data.defaultHours || { mode: "all" } );
	body.append( "<h2>Watering amount</h2><p class='small'>Weather changes when watering is due. The configured full event stays constant. Unknown values may remain blank in a draft.</p>" );
	var modes = [ { value: "runtime", label: "Minutes per watering (assumed refill)" }, { value: "depth", label: "Water depth per watering" } ];
	if ( program.sid !== undefined && ( !program.amountMode || program.amountMode === "legacy" ) ) { modes.push( { value: "legacy", label: "Existing deficit-based draft (legacy)" } ); }
	fields.amountMode = OSApp.SoilPrograms.select( body, "soil-amount-mode", "Specify watering amount", modes, program.amountMode || ( program.sid === undefined ? "runtime" : "legacy" ) );
	var runtimeBox = $( "<div></div>" ).appendTo( body ), depthBox = $( "<div></div>" ).appendTo( body ), calibration = $( "<div></div>" ).appendTo( body );
	fields.runtime = OSApp.SoilPrograms.durationField( runtimeBox, "soil-runtime", "Total ON time per watering", program.runtime );
	runtimeBox.append( "<p class='small'>A completed event is assumed to refill the zone. ETo and rainfall change frequency, not this runtime. Interrupted watering is not treated as a full refill. An event that cannot fit is skipped and reported.</p>" );
	fields.depth = OSApp.SoilPrograms.field( depthBox, "soil-depth", "Net water depth per watering (mm)", program.depth, "number" );
	calibration.append( "<h3>Water delivery</h3>" );
	fields.calibrationSource = OSApp.SoilPrograms.select( calibration, "soil-calibration-source", "Calibration method", [ { value: "manual", label: "Manual entry" }, { value: "catalogue", label: "Equipment catalog" } ], program.calibrationSource || "manual" );
	var manualBox = $( "<div id='soil-manual-calibration'></div>" ).appendTo( calibration ), catalogBox = $( "<div id='soil-catalogue-calibration'></div>" ).appendTo( calibration );
	fields.rate = OSApp.SoilPrograms.field( manualBox, "soil-rate", "Gross application rate (mm/hour)", program.rate, "number" );
	fields.efficiency = OSApp.SoilPrograms.field( manualBox, "soil-efficiency", "Application efficiency (%)", program.efficiency, "number" );
	equipmentSnapshot = OSApp.EquipmentCatalog.programHelper( catalogBox, fields, program );
	function calibrationVisibility() {
		var manual = fields.calibrationSource.val() === "manual";
		manualBox.show(); catalogBox.toggle( !manual );
		fields.rate.add( fields.efficiency ).prop( "disabled", !manual ).each( function() {
			if ( $( this ).data( "mobile-textinput" ) ) { $( this ).textinput( manual ? "enable" : "disable" ); }
		} );
	}
	fields.calibrationSource.on( "change", calibrationVisibility ); calibrationVisibility();
	function amountVisibility() {
		var mode = fields.amountMode.val();
		runtimeBox.toggle( mode === "runtime" ); depthBox.toggle( mode === "depth" ); calibration.toggle( mode !== "runtime" );
	}
	fields.amountMode.on( "change", amountVisibility ); amountVisibility();
	body.append( "<h2>Cycle & soak</h2><p class='small'>Split a watering event into short pulses. Other valves may run during a soak interval.</p>" );
	fields.cycle = OSApp.SoilPrograms.durationField( body, "soil-cycle", "Maximum ON per cycle", program.cycle );
	fields.soak = OSApp.SoilPrograms.durationField( body, "soil-soak", "Minimum soak between cycles", program.soak );
	fields.minimum = OSApp.SoilPrograms.durationField( body, "soil-minimum", "Minimum useful pulse", program.minimum );
	body.append( "<h3>Timing preview</h3><p class='small'>Preview uses the configured amount when available. The example is only used for incomplete or legacy drafts; it is never saved as the event duration.</p>" );
	var total = OSApp.SoilPrograms.durationField( body, "soil-example", "Example total ON time", 5 ), summary = $( "<p aria-live='polite'></p>" ).appendTo( body );
	function update() {
		var values = [ fields.amountMode.val() === "runtime" && fields.runtime.val() !== "" ? fields.runtime : total, fields.cycle, fields.soak ].map( function( button ) {
			var minutes = OSApp.SoilPrograms.durationMinutes( button );
			return minutes === "" ? NaN : minutes;
		} );
		if ( fields.amountMode.val() === "depth" && Number( fields.depth.val() ) > 0 && Number( fields.rate.val() ) > 0 && Number( fields.efficiency.val() ) > 0 ) {
			values[ 0 ] = Math.floor( Number( fields.depth.val() ) * 3600 / ( Number( fields.rate.val() ) * Number( fields.efficiency.val() ) / 100 ) ) / 60;
		}
		summary.text( OSApp.SoilPrograms.pulseSummary.apply( null, values ) );
	}
	page.on( "input change", "#soil-example, #soil-cycle, #soil-soak, #soil-runtime, #soil-depth, #soil-rate, #soil-efficiency, #soil-amount-mode", update );
	update();
	body.append( $( "<button class='ui-btn ui-btn-b'>Save draft</button>" ).on( "click", save ) );
	if ( sid !== undefined ) {
		body.append( $( "<button class='ui-btn'>Delete draft</button>" ).on( "click", function() {
			OSApp.UIDom.areYouSure( "Delete this soil-water program draft?", "", function() {
				data.programs = data.programs.filter( function( p ) { return p.sid !== sid; } );
				try { OSApp.SoilPrograms.save( data ); } catch ( e ) { return OSApp.Errors.showError( e.message ); }
				OSApp.UIDom.changePage( "#programs" );
			} );
		} ) );
	}
};

OSApp.SoilPrograms.settingsPage = function() {
	var data, excluded, shortage, profile = {}, windows, page;
	function save() {
		if ( !data ) { return; }

		var rules = [], valid = true;
		windows.children().each( function() {
			var row = $( this ), days = row.find( ":checkbox:checked" ).map( function() { return Number( this.value ); } ).get();
			var start = row.find( ".window-start" ).val(), end = row.find( ".window-end" ).val();
			if ( !days.length || !start || !end || start === end ) { valid = false; }
			rules.push( { days: days, start: start, end: end } );
		} );
		if ( !valid ) { return OSApp.Errors.showError( "Each window needs weekdays and distinct opening and closing times." ); }
		var dates = excluded.val().split( /[\s,]+/ ).filter( Boolean );
		if ( dates.some( function( d ) { return !/^\d{4}-\d{2}-\d{2}$/.test( d ) || !Number.isFinite( Date.parse( d ) ) || new Date( d ).toISOString().slice( 0, 10 ) !== d; } ) ) { return OSApp.Errors.showError( "Use valid excluded dates in YYYY-MM-DD format." ); }
		var values = {};
		for ( var key of Object.keys( profile ) ) {
			var raw = profile[ key ].val(), n = Number( raw );
			if ( raw !== "" && ( !Number.isFinite( n ) || n < 0 || ( n === 0 && ![ "crop", "rain" ].includes( key ) ) || ( [ "depletion", "rain" ].includes( key ) && n > 100 ) ) ) { return OSApp.Errors.showError( "Capacity, root depth and allowed depletion must be positive. Crop and rainfall factors may be zero; percentages cannot exceed 100." ); }
			values[ key ] = raw === "" ? "" : n;
		}
		try { data = OSApp.SoilPrograms.load(); } catch ( e ) { return OSApp.Errors.showError( e.message ); }
		data.windows = rules; data.excluded = dates.join( "\n" ); data.shortage = shortage.val(); data.profile = values;
		try { OSApp.SoilPrograms.save( data ); } catch ( e ) { return OSApp.Errors.showError( "Could not save draft: " + e.message ); }
		OSApp.Errors.showError( "Shared draft saved in this browser." );
	}
	page = OSApp.SoilPrograms.page( "soil-settings", "Soil-water settings", "#os-options", save );
	var body = page.find( "main" );
	try { data = OSApp.SoilPrograms.load(); } catch ( e ) { body.append( $( "<p></p>" ).text( e.message ) ); return; }
	body.append( "<h2>Legal watering windows</h2><p>Shared by all soil-water programs. No windows means no automatic watering. Times use controller local time. A closing time before opening crosses midnight; exclusions override windows.</p>" );
	windows = $( "<div></div>" ).appendTo( body );
	var nextWindow = 0;
	function addWindow( rule ) {
		var id = nextWindow++, row = $( "<fieldset></fieldset>" ).css( { padding: "12px", border: "1px solid #aaa", "border-radius": "5px", "margin-bottom": "12px" } ).appendTo( windows );
		$( "<legend>Watering window</legend>" ).appendTo( row );
		OSApp.SoilPrograms.field( row, "window-start-" + id, "Opens", rule.start, "time" ).addClass( "window-start" );
		OSApp.SoilPrograms.field( row, "window-end-" + id, "Closes", rule.end, "time" ).addClass( "window-end" );
		var days = $( "<fieldset data-role='controlgroup' data-type='horizontal' data-mini='true'><legend>Opening days</legend></fieldset>" ).appendTo( row );
		[ "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun" ].forEach( function( day, index ) {
			var checkbox = "window-day-" + id + "-" + index;
			$( "<input type='checkbox'>" ).attr( "id", checkbox ).val( index ).prop( "checked", ( rule.days || [] ).includes( index ) ).appendTo( days );
			$( "<label></label>" ).attr( "for", checkbox ).text( day ).appendTo( days );
		} );
		$( "<button class='ui-btn ui-mini'>Remove window</button>" ).appendTo( row ).on( "click", function() { row.remove(); } );
		if ( page.hasClass( "ui-page" ) ) { row.enhanceWithin(); }
	}
	data.windows.forEach( addWindow );
	body.append( $( "<button class='ui-btn'>Add watering window</button>" ).on( "click", function() { addWindow( {} ); } ) );
	body.append( "<label for='soil-excluded'>Excluded dates (YYYY-MM-DD, one per line)</label>" );
	excluded = $( "<textarea id='soil-excluded'></textarea>" ).val( data.excluded ).appendTo( body );
	body.append( "<h2>Capacity shortfalls</h2>" );
	shortage = OSApp.SoilPrograms.select( body, "soil-shortage", "When capacity is insufficient", [ { value: "report_only", label: "Report missed watering only" }, { value: "promote_next", label: "Report and promote for next window only" } ], data.shortage );
	body.append( "<p class='small'>Full events are preferred. Calibrated water-depth mode can use a sufficient partial event when capacity is short. Runtime mode needs a complete event or reports a skip. Promotion never changes the zone\u2019s assigned group; its size remains to be decided.</p><h2>Garden \xb7 shared site profile</h2><p class='small'>One profile initially; water balance is tracked separately for each valve. Blank values mean not yet calibrated.</p>" );
	[ [ "capacity", "Available water capacity (mm per meter of soil)" ], [ "roots", "Effective root depth (meters)" ], [ "depletion", "Allowed depletion (%)" ], [ "crop", "Crop coefficient" ], [ "rain", "Effective rainfall (%)" ] ].forEach( function( pair ) {
		profile[ pair[ 0 ] ] = OSApp.SoilPrograms.field( body, "profile-" + pair[ 0 ], pair[ 1 ], data.profile[ pair[ 0 ] ], "number" );
	} );
	body.append( "<p>Weather source: OpenSprinkler ETo service (planned).</p>" );
	body.append( $( "<button class='ui-btn ui-btn-b'>Save draft</button>" ).on( "click", save ) );
};

OSApp.SoilPrograms.previewPage = function() {
	OSApp.SoilPrograms.page( "preview", "Soil-water plan", "#sprinklers" ).find( "main" ).append(
		$( "<p></p>" ).text( "No automatic plan is available yet. Standard programs are retained and will resume when you select Standard scheduling." ),
		$( "<a href='#programs' class='ui-btn'>Edit soil-water programs</a>" ),
		$( "<p></p>" ).text( "Export your saved draft to evaluate it with the offline engine. Unsaved form edits are not included." ),
		$( "<button type='button' id='export-soil-draft' class='ui-btn'>Export saved draft</button>" ).on( "click", function() {
			try { OSApp.SoilPrograms.showDraftExport(); } catch ( e ) { OSApp.Errors.showError( e.message ); }
		} )
	);
};

// Export only the separate draft; never include controller credentials/config.
OSApp.SoilPrograms.exportDraft = function() {
	return JSON.stringify( OSApp.SoilPrograms.load(), null, 2 );
};

OSApp.SoilPrograms.showDraftExport = function() {
	var json = OSApp.SoilPrograms.exportDraft(), width = $.mobile.window.width(),
		popup = $( "<div data-role='popup' data-theme='a' id='soil-draft-export'><div class='ui-bar ui-bar-a'>Export saved draft</div><div class='ui-content'><p>Download the file, or copy this JSON into a local file for the offline engine.</p><label for='soil-draft-json'>Saved draft JSON</label><textarea id='soil-draft-json' class='textarea' rows='10' data-autogrow='false' readonly spellcheck='false'></textarea><a class='ui-btn' id='download-soil-draft' data-ajax='false' download='soil-water-draft.json'>Download file</a><button type='button' data-mini='true'>Close</button></div></div>" );
	popup.find( "textarea" ).val( json ).on( "focus", function() { this.select(); } );
	popup.find( "#download-soil-draft" ).attr( "href", "data:application/json;charset=utf-8," + encodeURIComponent( json ) );
	popup.find( "button" ).on( "click", function() { popup.popup( "close" ); } );
	popup.css( "width", width > 600 ? width * 0.6 + "px" : "100%" );
	OSApp.UIDom.openPopup( popup );
};
