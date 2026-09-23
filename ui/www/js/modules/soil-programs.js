/* global $, SunCalc */
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
		if ( ![ 1, 2, 3, 4 ].includes( data.version ) || !Array.isArray( data.programs ) || !Array.isArray( data.groups ) ) {
			throw new Error( "Unsupported soil-water draft. Stored data has not been changed." );
		}
		return data;
	}
	return { version: 3, programs: [], groups: [ "Normal" ], windows: [], excluded: "", shortage: "report_only", profile: {} };
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
				$( "<p></p>" ).css( "margin-bottom", 0 ).text( "Save draft stores these forms in this browser. On the test Pi, apply saved drafts separately in Virtual watering simulation. Production automatic watering is not connected." )
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
// Night uses dated astronomical events, never the firmware's default 06:00/18:00.
OSApp.SoilPrograms.nightPreview = function() {
	var coords = OSApp.currentSession.coordinates, settings = OSApp.currentSession.controller.settings || {},
		offset = OSApp.Dates.getTimezoneOffsetOS(), clock = new Date( settings.devt * 1000 );
	if ( !Array.isArray( coords ) || coords.length !== 2 || !coords.every( Number.isFinite ) || Math.abs( coords[ 0 ] ) > 90 || Math.abs( coords[ 1 ] ) > 180 || !Number.isFinite( clock.valueOf() ) || !Number.isFinite( offset ) ) {
		return "Set the controller location, date and timezone to calculate night hours.";
	}
	// devt is the controller's local wall clock encoded as epoch seconds.
	var noon = Date.UTC( clock.getUTCFullYear(), clock.getUTCMonth(), clock.getUTCDate(), 12 ) - offset * 60000,
		sunset = SunCalc.getTimes( new Date( noon ), coords[ 0 ], coords[ 1 ] ).sunset,
		sunrise = SunCalc.getTimes( new Date( noon + 86400000 ), coords[ 0 ], coords[ 1 ] ).sunrise;
	if ( !Number.isFinite( sunset.valueOf() ) || !Number.isFinite( sunrise.valueOf() ) || sunrise <= sunset ) {
		return "Sunrise or sunset is unavailable for this date and location. Night-only watering cannot be planned until valid times are available.";
	}
	function local( date ) {
		return new Date( date.valueOf() + offset * 60000 ).toISOString().slice( 0, 16 ).replace( "T", " " );
	}
	return "Calculated night: " + local( sunset ) + " to " + local( sunrise ) + " (controller local time). Recalculated for each date. Preview uses the controller's current timezone offset.";
};
OSApp.SoilPrograms.hoursSummary = function( value ) {
	if ( value && value.mode === "night" ) { return "Night only (sunset to sunrise)"; }
	return value && value.mode === "custom" ? value.start + " - " + value.end : "No restrictions";
};
OSApp.SoilPrograms.hoursControl = function( parent, id, value, inherited ) {
	value = value || { mode: inherited === undefined ? "all" : "inherit" };
	var inherit;
	if ( inherited !== undefined ) {
		var row = $( "<div class='ui-field-contain'></div>" ).appendTo( parent );
		inherit = $( "<input type='checkbox' data-mini='true'>" ).attr( "id", id + "-inherit" ).prop( "checked", value.mode === "inherit" ).appendTo( row );
		$( "<label></label>" ).attr( "for", id + "-inherit" ).text( "Use default: " + OSApp.SoilPrograms.hoursSummary( inherited ) ).appendTo( row );
	}
	var effective = value.mode === "inherit" ? inherited : value,
		controls = $( "<div></div>" ).appendTo( parent ),
		mode = OSApp.SoilPrograms.select( controls, id + "-mode", "Watering hours", [ { value: "all", label: "No restrictions" }, { value: "custom", label: "Set allowed hours" } ], effective.mode === "all" ? "all" : "custom" ),
		box = $( "<div></div>" ).appendTo( controls ),
		kind = OSApp.SoilPrograms.select( box, id + "-kind", "Allowed hours", [ { value: "custom", label: "Choose times" }, { value: "night", label: "Night only" } ], effective.mode === "night" ? "night" : "custom" ),
		times = $( "<div></div>" ).appendTo( box ),
		start = OSApp.SoilPrograms.field( times, id + "-start", "From", effective.start, "time" ),
		end = OSApp.SoilPrograms.field( times, id + "-end", "Until", effective.end, "time" ),
		night = $( "<p class='small'></p>" ).text( "Sunset to the following sunrise. " + OSApp.SoilPrograms.nightPreview() ).appendTo( box );
	parent.append( "<p class='small'>Controller local time. An end before the start crosses midnight. Every watering pulse must finish within allowed hours. Any separately configured calendar restrictions and excluded dates still apply.</p>" );
	function visibility() {
		controls.toggle( !inherit || !inherit.prop( "checked" ) );
		box.toggle( mode.val() === "custom" ); times.toggle( kind.val() !== "night" ); night.toggle( kind.val() === "night" );
	}
	if ( inherit ) { inherit.on( "change", visibility ); }
	mode.add( kind ).on( "change", visibility ); visibility();
	return function() {
		if ( inherit && inherit.prop( "checked" ) ) { return { mode: "inherit" }; }
		var result = { mode: mode.val() === "all" ? "all" : kind.val() };
		if ( result.mode === "custom" ) {
			result.start = start.val(); result.end = end.val();
			if ( ![ result.start, result.end ].every( function( t ) { return /^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/.test( t ); } ) || result.start === result.end ) {
				throw new Error( "Enter distinct allowed start and end times, or select No restrictions." );
			}
		}
		return result;
	};
};
OSApp.SoilPrograms.defaultHoursControl = function( parent ) {
	var data;
	try { data = OSApp.SoilPrograms.load(); } catch ( e ) { parent.append( $( "<p></p>" ).text( e.message ) ); return; }
	parent.append( "<h3>Default watering hours</h3><p class='small'>Programs using the default follow later changes automatically. Saved as a browser-local draft.</p>" );
	var read = OSApp.SoilPrograms.hoursControl( parent, "soil-default-hours", data.defaultHours ), status = $( "<p role='status'></p>" );
	parent.append( $( "<button type='button' class='ui-btn ui-mini noselect'>Save default hours draft</button>" ).on( "click", function() {
		try {
			var hours = read(), latest = OSApp.SoilPrograms.load();
			latest.version = Math.max( 3, latest.version ); latest.defaultHours = hours; OSApp.SoilPrograms.save( latest );
			status.text( "Default watering hours saved." );
		} catch ( e ) { OSApp.Errors.showError( e.message ); }
	} ), status );
	parent.find( ":input" ).addClass( "noselect" );
	parent.on( "change input", function( event ) { event.stopPropagation(); } );
};
OSApp.SoilPrograms.programKey = function( program ) { return program.scheduleMode === "fixed" ? program.id : program.sid; };
// Optional owner-provided starter set served by the dedicated DEMO UI host.
// Apply once per browser/controller, preserving edited programs and site settings.
OSApp.SoilPrograms.applyStarters = function( seed ) {
	var controller = OSApp.currentSession.controller;
	if ( controller.options.hwv !== 255 || !seed || seed.version !== 1 || !seed.id ||
		JSON.stringify( seed.stationNames ) !== JSON.stringify( controller.stations.snames ) || !Array.isArray( seed.programs ) ) { return false; }
	var marker = OSApp.SoilPrograms.storageKey() + ":starter:" + seed.id;
	if ( OSApp.Storage.getItemSync( marker ) ) { return false; }
	var data = OSApp.SoilPrograms.load(), before = JSON.stringify( data ), seen = [], eligible = OSApp.SoilPrograms.eligibleZones().map( function( z ) { return z.sid; } );
	seed.programs.forEach( function( p ) {
		if ( !Number.isInteger( p.sid ) || seen.includes( OSApp.SoilPrograms.programKey( p ) ) || !eligible.includes( p.sid ) || !p.name || p.amountMode !== "runtime" || ( p.scheduleMode !== "fixed" && p.profile !== "garden" ) || ( p.scheduleMode === "fixed" && ( typeof p.id !== "string" || !p.id.startsWith( "timed:" ) ) ) ) {
			throw new Error( "Starter programs do not match the available valves." );
		}
		seen.push( OSApp.SoilPrograms.programKey( p ) );
	} );
	seed.programs.forEach( function( p ) {
		var existing = data.programs.find( function( saved ) { return OSApp.SoilPrograms.programKey( saved ) === OSApp.SoilPrograms.programKey( p ); } );
		// Only replace a byte-for-byte match to an explicitly supplied example.
		var example = existing && ( seed.replaceExamples || [] ).some( function( original ) { return JSON.stringify( original ) === JSON.stringify( existing ); } );
		if ( existing && !example ) { return; }
		var copy = JSON.parse( JSON.stringify( p ) );
		if ( !data.groups.includes( copy.group ) ) { copy.group = data.groups[ 0 ]; }
		data.programs = data.programs.filter( function( saved ) { return OSApp.SoilPrograms.programKey( saved ) !== OSApp.SoilPrograms.programKey( copy ); } );
		data.programs.push( copy );
	} );
	data.programs.sort( function( a, b ) { return a.sid - b.sid; } ); data.version = 4;
	OSApp.Storage.setItemSync( marker + ":backup", before );
	OSApp.SoilPrograms.save( data );
	OSApp.Storage.setItemSync( marker, "applied" );
	return true;
};
OSApp.SoilPrograms.fetchStarters = function( page, done ) {
	var key = OSApp.SoilPrograms.storageKey(), controller = OSApp.currentSession.controller, jsp = ( controller.settings || {} ).jsp;
	if ( controller.options.hwv !== 255 || !jsp ) { return; }
	$.getJSON( jsp.replace( /\/$/, "" ) + "/soil-starter-programs.json" ).done( function( seed ) {
		if ( key !== OSApp.SoilPrograms.storageKey() || !$.contains( document, page[ 0 ] ) ) { return; }
		try { if ( OSApp.SoilPrograms.applyStarters( seed ) ) { done(); } } catch ( e ) { OSApp.Errors.showError( e.message ); }
	} );
};
OSApp.SoilPrograms.displayPage = function() {
	var page = OSApp.SoilPrograms.page( "programs", OSApp.Language._( "Programs" ), "#sprinklers", null, {
		icon: "plus",
		text: OSApp.Language._( "Add" ),
		on: function() { OSApp.UIDom.changePage( "#addprogram" ); }
	} ), body = page.find( "main" ), data;
	function render() {
		body.empty();
		if ( OSApp.currentSession.controller.options.hwv === 255 ) { body.append( "<a href='#preview' class='ui-btn ui-mini'>Virtual watering simulation</a>" ); }
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
			button.append( $( "<div class='small'></div>" ).text( name + " \xb7 " + program.group + " \xb7 " + ( program.scheduleMode === "fixed" ? "Fixed days, times and watering duration" : "Soil water balance" ) + " \xb7 " + ( program.enabled ? "Enabled draft" : "Disabled draft" ) ) );
			button.on( "click", function() { OSApp.UIDom.changePage( "#addprogram", { soilZone: OSApp.SoilPrograms.programKey( program ) } ); return false; } );
			body.append( button );
		} );
	}
	render();
	OSApp.SoilPrograms.fetchStarters( page, render );
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
		if ( fields.scheduleMode.val() !== "fixed" && data.programs.some( function( p ) { return p.scheduleMode !== "fixed" && p.sid === chosen && OSApp.SoilPrograms.programKey( p ) !== originalSid; } ) ) {
			return OSApp.Errors.showError( "This valve already has a soil-water program." );
		}
		if ( !fields.name.val().trim() ) { return OSApp.Errors.showError( "Enter a program name." ); }
		var equipment;
		try { equipment = fields.scheduleMode.val() !== "fixed" && fields.amountMode.val() !== "runtime" && fields.calibrationSource.val() === "catalogue" ? equipmentSnapshot() : undefined; } catch ( e ) { return OSApp.Errors.showError( e.message ); }
		var result = { calibrationSource: fields.calibrationSource.val(), sid: chosen, name: fields.name.val().trim(), profile: "garden", group: fields.group.val(), enabled: fields.enabled.prop( "checked" ) };
		try { result.permittedHours = readHours(); } catch ( e ) { return OSApp.Errors.showError( e.message ); }
		result.amountMode = fields.scheduleMode.val() === "fixed" ? "runtime" : fields.amountMode.val();
		for ( var key of ( fields.scheduleMode.val() === "fixed" ? [ "cycle", "soak", "minimum", "runtime" ] : [ "rate", "efficiency", "cycle", "soak", "minimum", "runtime", "depth" ] ) ) {
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
		if ( fields.scheduleMode.val() === "fixed" ) {
			var days = fixedBox.find( ":checkbox:checked" ).map( function() { return Number( this.value ); } ).get(),
				times = fields.times.val().split( /[\s,]+/ ).filter( Boolean );
			if ( !days.length || !times.length || new Set( times ).size !== times.length || times.some( function( t ) { return !/^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/.test( t ); } ) ) {
				return OSApp.Errors.showError( "Select weekdays and enter distinct start times in HH:MM format." );
			}
			if ( !( result.runtime > 0 && result.cycle > 0 && result.minimum > 0 ) || result.soak === "" ) {
				return OSApp.Errors.showError( "Set runtime and cycle settings for fixed-time watering." );
			}
			result = { id: program.id || "timed:" + Date.now() + ":" + Math.random().toString( 36 ).slice( 2 ),
				scheduleMode: "fixed", sid: chosen, name: result.name, enabled: result.enabled, group: result.group,
				permittedHours: result.permittedHours, amountMode: "runtime", runtime: result.runtime,
				cycle: result.cycle, soak: result.soak, minimum: result.minimum, days: days, times: times.sort() };
		}
		data.version = fields.scheduleMode.val() === "fixed" ? 4 : Math.max( 3, data.version );
		data.programs = data.programs.filter( function( p ) { return OSApp.SoilPrograms.programKey( p ) !== originalSid; } ).concat( [ result ] );
		try { OSApp.SoilPrograms.save( data ); } catch ( e ) { return OSApp.Errors.showError( "Could not save draft: " + e.message ); }
		OSApp.UIDom.changePage( "#programs" );
	}
	page = OSApp.SoilPrograms.page( "addprogram", sid === undefined ? "Add program" : "Edit program", "#programs", save );
	var body = page.find( "main" );
	try { data = OSApp.SoilPrograms.load(); } catch ( e ) { body.append( $( "<p></p>" ).text( e.message ) ); return; }
	program = data.programs.find( function( p ) { return OSApp.SoilPrograms.programKey( p ) === sid; } ) || { enabled: true, group: data.groups[ 0 ] };
	var zones = OSApp.SoilPrograms.eligibleZones();
	if ( !zones.length ) { body.append( "<p>No individual valves are enabled.</p>" ); return; }
	fields.scheduleMode = OSApp.SoilPrograms.select( body, "soil-schedule-mode", "Schedule by", [ { value: "soil", label: "Soil water balance" }, { value: "fixed", label: "Fixed days, times and watering duration" } ], program.scheduleMode || "soil" );
	body.append( "<h2>Valve & priority</h2>" );
	fields.zone = OSApp.SoilPrograms.select( body, "soil-zone", "Zone / valve", [], program.sid );
	function zoneChoices() {
		var selected = fields.zone.val();
		fields.zone.empty();
		zones.filter( function( zone ) { return fields.scheduleMode.val() === "fixed" || zone.sid === program.sid || !data.programs.some( function( p ) { return p.scheduleMode !== "fixed" && p.sid === zone.sid; } ); } ).forEach( function( zone ) {
			$( "<option></option>" ).val( zone.sid ).text( zone.name ).appendTo( fields.zone );
		} );
		if ( fields.zone.find( "option" ).filter( function() { return this.value === selected; } ).length ) { fields.zone.val( selected ); }
		if ( fields.zone.data( "mobile-selectmenu" ) ) { fields.zone.selectmenu( "refresh" ); }
	}
	zoneChoices(); if ( program.sid !== undefined ) { fields.zone.val( program.sid ); }

	body.append( OSApp.Programs.makeNameField( "soil-name", program.name || ( zones.find( function( z ) { return z.sid === Number( fields.zone.val() ); } ) || zones[ 0 ] ).name ),
		OSApp.Programs.makeEnabledField( "soil-enabled", program.enabled ) );
	fields.name = body.find( "#soil-name" );
	fields.enabled = body.find( "#soil-enabled" );
	var profileField = OSApp.SoilPrograms.select( body, "soil-profile", "Site profile", [ { value: "garden", label: "Garden (shared)" } ], "garden" );
	fields.group = OSApp.SoilPrograms.select( body, "soil-group", "Priority group", data.groups.map( function( g ) { return { value: g, label: g }; } ), program.group );
	body.append( "<h2>Watering hours</h2>" );
	readHours = OSApp.SoilPrograms.hoursControl( $( "<div></div>" ).appendTo( body ), "soil-hours", program.permittedHours, data.defaultHours || { mode: "all" } );
	body.append( "<h2>Watering amount</h2>" );
	var modes = [ { value: "runtime", label: "Minutes per watering (assumed refill)" }, { value: "depth", label: "Water depth per watering" } ];
	if ( program.sid !== undefined && ( !program.amountMode || program.amountMode === "legacy" ) ) { modes.push( { value: "legacy", label: "Existing deficit-based draft (legacy)" } ); }
	fields.amountMode = OSApp.SoilPrograms.select( body, "soil-amount-mode", "Specify watering amount", modes, program.amountMode || ( program.sid === undefined ? "runtime" : "legacy" ) );
	var fixedBox = $( "<div id='soil-fixed-schedule'></div>" ).appendTo( body );
	var runtimeBox = $( "<div></div>" ).appendTo( body ), depthBox = $( "<div></div>" ).appendTo( body ), calibration = $( "<div></div>" ).appendTo( body );
	fields.runtime = OSApp.SoilPrograms.durationField( runtimeBox, "soil-runtime", "Total ON time per watering", program.runtime );
	var refillHelp = $( "<p class='small'>A completed event is assumed to refill the zone. ETo and rainfall change frequency, not this runtime. Interrupted watering is not treated as a full refill. An event that cannot fit is skipped and reported.</p>" ).appendTo( runtimeBox );
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
	var weekdays = $( "<fieldset data-role='controlgroup' data-type='horizontal' data-mini='true'><legend>Run on</legend></fieldset>" ).appendTo( fixedBox );
	[ "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun" ].forEach( function( day, index ) {
		var id = "soil-fixed-day-" + index;
		$( "<input type='checkbox'>" ).attr( "id", id ).val( index ).prop( "checked", ( program.days || [] ).includes( index ) ).appendTo( weekdays );
		$( "<label></label>" ).attr( "for", id ).text( day ).appendTo( weekdays );
	} );
	fields.times = OSApp.SoilPrograms.field( fixedBox, "soil-fixed-times", "Start times (HH:MM)", ( program.times || [] ).join( ", " ), "text", "Controller local time. Separate multiple times with commas, for example 12:15, 15:00." );
	fixedBox.append( "<p class='small'>Fixed runtime on the selected days, without ETo adjustment. Suitable for misting: no soil refill is assumed. Watering restrictions still apply. A blocked or conflicting event is skipped and reported, not delayed or caught up. Fixed-time slots are reserved before flexible soil watering; priority groups resolve competing fixed-time slots.</p>" );
	function amountVisibility() {
		var fixed = fields.scheduleMode.val() === "fixed", mode = fields.amountMode.val();
		fixedBox.toggle( fixed ); profileField.closest( ".ui-field-contain" ).toggle( !fixed );
		fields.amountMode.closest( ".ui-field-contain" ).toggle( !fixed ); refillHelp.toggle( !fixed );
		runtimeBox.toggle( fixed || mode === "runtime" ); depthBox.toggle( !fixed && mode === "depth" ); calibration.toggle( !fixed && mode !== "runtime" );
	}
	fields.scheduleMode.on( "change", function() { zoneChoices(); amountVisibility(); } );
	fields.amountMode.on( "change", amountVisibility ); amountVisibility();
	body.append( "<h2>Cycle & soak</h2><p class='small'>Split a watering event into short pulses. Other valves may run during a soak interval.</p>" );
	fields.cycle = OSApp.SoilPrograms.durationField( body, "soil-cycle", "Maximum ON per cycle", program.cycle );
	fields.soak = OSApp.SoilPrograms.durationField( body, "soil-soak", "Minimum soak between cycles", program.soak );
	fields.minimum = OSApp.SoilPrograms.durationField( body, "soil-minimum", "Minimum useful pulse", program.minimum );
	body.append( "<h3>Timing preview</h3><p class='small'>Preview uses the configured amount when available. The example is only used for incomplete or legacy drafts; it is never saved as the event duration.</p>" );
	var total = OSApp.SoilPrograms.durationField( body, "soil-example", "Example total ON time", 5 ), summary = $( "<p aria-live='polite'></p>" ).appendTo( body );
	function update() {
		var values = [ ( fields.scheduleMode.val() === "fixed" || fields.amountMode.val() === "runtime" ) && fields.runtime.val() !== "" ? fields.runtime : total, fields.cycle, fields.soak ].map( function( button ) {
			var minutes = OSApp.SoilPrograms.durationMinutes( button );
			return minutes === "" ? NaN : minutes;
		} );
		if ( fields.scheduleMode.val() !== "fixed" && fields.amountMode.val() === "depth" && Number( fields.depth.val() ) > 0 && Number( fields.rate.val() ) > 0 && Number( fields.efficiency.val() ) > 0 ) {
			values[ 0 ] = Math.floor( Number( fields.depth.val() ) * 3600 / ( Number( fields.rate.val() ) * Number( fields.efficiency.val() ) / 100 ) ) / 60;
		}
		summary.text( OSApp.SoilPrograms.pulseSummary.apply( null, values ) );
	}
	page.on( "input change", "#soil-example, #soil-cycle, #soil-soak, #soil-runtime, #soil-depth, #soil-rate, #soil-efficiency, #soil-amount-mode, #soil-schedule-mode", update );
	update();
	body.append( $( "<button class='ui-btn ui-btn-b'>Save draft</button>" ).on( "click", save ) );
	if ( sid !== undefined ) {
		body.append( $( "<button class='ui-btn'>Delete draft</button>" ).on( "click", function() {
			OSApp.UIDom.areYouSure( "Delete this program draft?", "", function() {
				try { data = OSApp.SoilPrograms.load(); } catch ( e ) { return OSApp.Errors.showError( e.message ); }
				data.programs = data.programs.filter( function( p ) { return OSApp.SoilPrograms.programKey( p ) !== sid; } );
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
		data.version = Math.max( 3, data.version ); data.windows = rules; data.excluded = dates.join( "\n" ); data.shortage = shortage.val(); data.profile = values;
		try { OSApp.SoilPrograms.save( data ); } catch ( e ) { return OSApp.Errors.showError( "Could not save draft: " + e.message ); }
		OSApp.Errors.showError( "Shared draft saved in this browser." );
	}
	page = OSApp.SoilPrograms.page( "soil-settings", "Soil-water settings", "#os-options", save );
	var body = page.find( "main" );
	try { data = OSApp.SoilPrograms.load(); } catch ( e ) { body.append( $( "<p></p>" ).text( e.message ) ); return; }
	body.append( "<h2>Optional calendar restrictions</h2><p>Shared by all soil-water programs. Leave empty for no additional calendar restrictions. Add windows only to restrict watering to particular weekdays and times. Times use controller local time; exclusions always apply. A closing time before opening crosses midnight.</p>" );
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
	if ( data.version < 3 && !data.windows.length ) { body.append( "<p>Legacy draft: watering remains blocked until you save these settings. Saving an empty calendar now means no calendar restrictions.</p>" ); }
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

OSApp.SoilPrograms.simulationPanel = function( page ) {
	var c = OSApp.currentSession.controller, jsp = ( c.settings || {} ).jsp;
	if ( c.options.hwv !== 255 || !jsp ) { return; }
	var url = jsp.replace( /\/js\/?$/, "" ) + "/simulation", box = $( "<section id='soil-simulation'></section>" ).appendTo( page.find( "main" ) ), timer, request, closed = false;
	box.append( "<h2>Virtual watering simulation</h2><p>Fake valves only. This test uses an accelerated clock, synthetic weather and temporary values for blank soil-profile fields. Your saved field calibration is not changed.</p>" );
	var status = $( "<p role='status'>Connecting to the test Pi...</p>" ).appendTo( box ),
		buttons = $( "<div></div>" ).appendTo( box ), details = $( "<div></div>" ).appendTo( box );
	function render( data ) {
		status.text( ( data.running ? "Running" : "Paused" ) + " - virtual time " + data.local_time + " - " + data.speed + "x clock" + ( data.error ? " - " + data.error : "" ) );
		details.empty();
		$( "<p></p>" ).text( "Active virtual valve: " + ( data.active.map( function( a ) { return a.name; } ).join( ", " ) || "None" ) ).appendTo( details );
		if ( data.profile ) { $( "<p class='small'></p>" ).text( "Effective test profile: " + JSON.stringify( data.profile ) + ". Assumed fields: " + ( data.assumed_profile_fields.join( ", " ) || "none" ) ).appendTo( details ); }
		$( "<p class='small'></p>" ).text( data.assumptions.join( ". " ) ).appendTo( details );
		if ( data.plan ) {
			details.append( "<h3>Current plan</h3>" );
			var plan = $( "<ul></ul>" ).appendTo( details );
			data.plan.decisions.forEach( function( d ) { $( "<li></li>" ).text( d.name + ": " + d.status + " (" + d.reason + ")" + ( d.seconds ? " - " + d.seconds + " seconds ON" : "" ) ).appendTo( plan ); } );
		}
		if ( Object.keys( data.balances ).length ) {
			details.append( "<h3>Simulated soil depletion</h3>" );
			var balances = $( "<ul></ul>" ).appendTo( details );
			Object.keys( data.balances ).forEach( function( sid ) { $( "<li></li>" ).text( ( c.stations.snames[ Number( sid ) ] || "Valve " + ( Number( sid ) + 1 ) ) + ": " + data.balances[ sid ].toFixed( 2 ) + " mm" ).appendTo( balances ); } );
		}
		details.append( "<h3>Recent simulation events</h3>" );
		var history = $( "<ul></ul>" ).appendTo( details );
		data.records.slice( -30 ).reverse().forEach( function( event ) {
			var time = new Date( event.at * 1000 ).toLocaleString( undefined, { timeZone: data.timezone } );
			$( "<li></li>" ).text( time + " - " + event.kind + ( event.name ? ": " + event.name : "" ) + ( event.detail ? " - " + event.detail : "" ) + ( event.kind === "completed" ? ( event.refill ? " - assumed refill recorded" : " - no assumed refill" ) : "" ) ).appendTo( history );
		} );
	}
	function failed( xhr ) { status.text( "Simulation unavailable: " + ( xhr.responseJSON && xhr.responseJSON.error || "check the test Pi service" ) ); }
	function poll() {
		if ( closed ) { return; }
		request = $.ajax( { url: url + "/status", dataType: "json", timeout: 5000 } ).done( render ).fail( failed ).always( function() {
			if ( !closed ) { timer = setTimeout( poll, 2000 ); }
		} );
	}
	function post( path, body ) {
		buttons.find( "button" ).prop( "disabled", true );
		$.ajax( { url: url + path, method: "POST", contentType: "application/json", data: JSON.stringify( body ), dataType: "json", timeout: 10000 } )
			.done( render ).fail( failed ).always( function() { buttons.find( "button" ).prop( "disabled", false ); } );
	}
	buttons.append( $( "<button type='button' class='ui-btn'>Apply saved drafts to simulation</button>" ).on( "click", function() {
		try { post( "/config", OSApp.SoilPrograms.load() ); } catch ( e ) { OSApp.Errors.showError( e.message ); }
	} ), $( "<button type='button' class='ui-btn'>Pause simulation</button>" ).on( "click", function() { post( "/control", { action: "pause" } ); } ),
	$( "<button type='button' class='ui-btn'>Resume simulation</button>" ).on( "click", function() { post( "/control", { action: "resume" } ); } ) );
	page.one( "pagehide", function() { closed = true; clearTimeout( timer ); if ( request ) { request.abort(); } } );
	poll();
};
OSApp.SoilPrograms.previewPage = function() {
	var page = OSApp.SoilPrograms.page( "preview", "Soil-water plan", "#sprinklers" );
	page.find( "main" ).append(
		$( "<a href='#programs' class='ui-btn'>Edit programs</a>" ),
		$( "<p></p>" ).text( "Standard programs are retained. Production execution of the new model is not connected. Export saved drafts for offline evaluation, or use the dedicated test Pi simulation below." ),
		$( "<button type='button' id='export-soil-draft' class='ui-btn'>Export saved draft</button>" ).on( "click", function() {
			try { OSApp.SoilPrograms.showDraftExport(); } catch ( e ) { OSApp.Errors.showError( e.message ); }
		} )
	);
	OSApp.SoilPrograms.simulationPanel( page );
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
