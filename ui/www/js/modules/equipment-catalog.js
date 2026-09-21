/* global $ */
/* OpenSprinkler App - AGPL-3.0; see ui/LICENSE. */
var OSApp = OSApp || {};
OSApp.EquipmentCatalog = OSApp.EquipmentCatalog || {};
OSApp.EquipmentCatalog.key = "irrigationEquipmentCatalog:v1";
OSApp.EquipmentCatalog.types = [
	{ value: "dripline", label: "Integrated dripline (L/hour per emitter)" },
	{ value: "emitter", label: "Individual dripper / sprinkler (L/hour each)" },
	{ value: "hose", label: "Porous hose (L/hour per metre)" },
	{ value: "rate", label: "Application rate (mm/hour)" }
];
// Product examples only: no efficiency or installation layout is prescribed.
OSApp.EquipmentCatalog.defaults = function() {
	return { version: 1, entries: [
		{ id: "jardibric-a1480", name: "Jardibric Aqua Gout’ A1480", type: "dripline", flow: 2, spacing: 0.33, efficiency: "", conditions: "2 L/hour per emitter at 1 bar; 33 cm emitter spacing. Match the installed product.", source: "https://jardibric.com/wp-content/uploads/2021/06/Catalogue_JARDIBRIC_2023_EN_GENERAL.pdf#page=46" },
		{ id: "netafim-unitechline16-30", name: "Netafim UNITECHLINE 16 — 1.6 L/h, 30 cm", type: "dripline", flow: 1.6, spacing: 0.3, efficiency: "", conditions: "0.5–4 bar; this entry is the 30 cm variant. Buried turf product.", source: "https://www.netafim.fr/contentassets/522e1449f2b643b1889cbe1e3093d65b/irrig-enterre-pj.pdf" },
		{ id: "rainbird-xfd-23-305", name: "Rain Bird XFD — 2.3 L/h, 30.5 cm", type: "dripline", flow: 2.3, spacing: 0.305, efficiency: "", conditions: "0.58–4.1 bar. Match the 30.5 cm variant; other regional spacings exist.", source: "https://www.rainbird.com/fr/products/goutteur-en-ligne-de-surface-xfd" },
		{ id: "hunter-pld22-30", name: "Hunter PLD-22 — 2.2 L/h, 30 cm", type: "dripline", flow: 2.2, spacing: 0.3, efficiency: "", conditions: "PLD 16 mm, 30 cm variant. Verify operating limits and installed model against the datasheet.", source: "https://www.hunterirrigation.com/sites/default/files/CA-Cutsheet-PLD-FR.pdf" },
		{ id: "claber-91249", name: "Claber 91249 — at 1.5 bar", type: "emitter", flow: 46, spacing: "", efficiency: "", conditions: "46 L/hour at 1.5 bar; adjustable sprinkler. Verify its setting and actual coverage.", source: "https://www.claber.com/fr/prodotti/scheda/91249/Micro-asperseur-360-reglable" }
	] };
};
OSApp.EquipmentCatalog.validate = function( data ) {
	if ( !data || data.version !== 1 || !Array.isArray( data.entries ) ) { throw new Error( "Unsupported equipment catalogue." ); }
	var ids = new Set(), names = new Set();
	data.entries.forEach( function( e ) {
		if ( !e || typeof e.id !== "string" || !e.id.trim() || ids.has( e.id ) || typeof e.name !== "string" || !e.name.trim() || names.has( e.name.trim().toLowerCase() ) ) { throw new Error( "Each catalogue entry needs a unique ID and name." ); }
		ids.add( e.id ); names.add( e.name.trim().toLowerCase() );
		if ( !OSApp.EquipmentCatalog.types.some( function( t ) { return t.value === e.type; } ) || !Number.isFinite( e.flow ) || e.flow <= 0 ) { throw new Error( "Choose an equipment type and positive flow or rate." ); }
		if ( e.type === "dripline" && ( !Number.isFinite( e.spacing ) || e.spacing <= 0 ) ) { throw new Error( "Emitter spacing must be positive." ); }
		if ( e.efficiency !== "" && ( !Number.isFinite( e.efficiency ) || e.efficiency <= 0 || e.efficiency > 100 ) ) { throw new Error( "Efficiency must be blank or greater than 0 and at most 100%." ); }
		if ( typeof e.source !== "string" || typeof e.conditions !== "string" ) { throw new Error( "Source and operating conditions must be text." ); }
	} );
	return data;
};
OSApp.EquipmentCatalog.load = function() {
	var raw = OSApp.Storage.getItemSync( OSApp.EquipmentCatalog.key );
	return OSApp.EquipmentCatalog.validate( raw ? JSON.parse( raw ) : OSApp.EquipmentCatalog.defaults() );
};
OSApp.EquipmentCatalog.save = function( baseline, data ) {
	if ( JSON.stringify( OSApp.EquipmentCatalog.load() ) !== JSON.stringify( baseline ) ) { throw new Error( "Catalogue changed in another window. Reopen before saving." ); }
	OSApp.EquipmentCatalog.validate( data );
	OSApp.Storage.setItemSync( OSApp.EquipmentCatalog.key, JSON.stringify( data ) );
};
OSApp.EquipmentCatalog.calculate = function( entry, geometry ) {
	OSApp.EquipmentCatalog.validate( { version: 1, entries: [ entry ] } );
	function positive( key ) {
		var n = Number( geometry[ key ] );
		if ( !Number.isFinite( n ) || n <= 0 ) { throw new Error( "Enter positive layout values." ); }
		return n;
	}
	var rate = entry.flow;
	if ( entry.type === "dripline" ) { rate /= entry.spacing * positive( "rows" ); }
	if ( entry.type === "emitter" ) {
		var count = positive( "count" );
		if ( !Number.isInteger( count ) ) { throw new Error( "Emitter count must be a whole number." ); }
		rate *= count / positive( "area" );
	}
	if ( entry.type === "hose" ) { rate *= positive( "length" ) / positive( "area" ); }
	if ( !Number.isFinite( rate ) || rate <= 0 ) { throw new Error( "Calculated application rate is out of range." ); }
	return rate;
};
OSApp.EquipmentCatalog.displayPage = function() {
	var page = OSApp.SoilPrograms.page( "equipment-catalog", "Equipment catalogue", "#os-options" ), body = page.find( "main" ), data, baseline;
	if ( OSApp.currentSession.controller.options.smode !== 1 ) { body.append( "<p>Select and save Soil water balance to manage the catalogue.</p>" ); return; }
	try { data = OSApp.EquipmentCatalog.load(); baseline = JSON.parse( JSON.stringify( data ) ); } catch ( e ) { body.append( $( "<p></p>" ).text( e.message ) ); return; }
	body.append( "<p>Add, edit or remove equipment as you identify it. Entries are stored in this browser and shared across its controller drafts. Existing programs keep their copied values.</p>" );
	var list = $( "<div></div>" ).appendTo( body ), editor = $( "<div></div>" ).appendTo( body );
	function persist( next ) {
		try { OSApp.EquipmentCatalog.save( baseline, next ); } catch ( e ) { OSApp.Errors.showError( e.message ); return false; }
		data = next; baseline = JSON.parse( JSON.stringify( next ) ); return true;
	}
	function render() {
		list.empty();
		data.entries.forEach( function( entry ) {
			$( "<button class='ui-btn catalog-entry'></button>" ).text( entry.name ).appendTo( list ).on( "click", function() { edit( entry ); } );
		} );
		$( "<button id='add-equipment' class='ui-btn'>Add equipment</button>" ).appendTo( list ).on( "click", function() { edit(); } );
	}
	function edit( entry ) {
		editor.empty();
		var e = entry || { name: "", type: "dripline", flow: "", spacing: "", efficiency: "", conditions: "", source: "" }, fields = {};
		editor.append( "<h2>Equipment details</h2>" );
		fields.name = OSApp.SoilPrograms.field( editor, "catalog-name", "Name / model", e.name );
		fields.type = OSApp.SoilPrograms.select( editor, "catalog-type", "Type", OSApp.EquipmentCatalog.types, e.type );
		fields.flow = OSApp.SoilPrograms.field( editor, "catalog-flow", "Flow / application rate (units above)", e.flow, "number" );
		fields.spacing = OSApp.SoilPrograms.field( editor, "catalog-spacing", "Emitter spacing (metres, dripline only)", e.spacing, "number" );
		fields.efficiency = OSApp.SoilPrograms.field( editor, "catalog-efficiency", "Estimated efficiency (%) — optional", e.efficiency, "number" );
		fields.conditions = OSApp.SoilPrograms.field( editor, "catalog-conditions", "Pressure, settings and other assumptions", e.conditions );
		fields.source = OSApp.SoilPrograms.field( editor, "catalog-source", "Source / reference", e.source );
		function visibility() { fields.spacing.closest( ".ui-field-contain" ).toggle( fields.type.val() === "dripline" ); }
		fields.type.on( "change", visibility ); visibility();
		$( "<button id='save-equipment' class='ui-btn ui-btn-b'>Save equipment</button>" ).appendTo( editor ).on( "click", function() {
			var item = { id: entry ? entry.id : "custom-" + Date.now() + "-" + Math.random().toString( 36 ).slice( 2 ) };
			Object.keys( fields ).forEach( function( key ) {
				var value = fields[ key ].val().trim();
				item[ key ] = [ "flow", "spacing", "efficiency" ].includes( key ) && value !== "" ? Number( value ) : value;
			} );
			var next = { version: 1, entries: data.entries.filter( function( old ) { return old.id !== item.id; } ).concat( [ item ] ) };
			if ( persist( next ) ) { editor.empty(); render(); }
		} );
		if ( entry ) {
			$( "<button id='delete-equipment' class='ui-btn'>Delete equipment</button>" ).appendTo( editor ).on( "click", function() {
				OSApp.UIDom.areYouSure( "Delete this catalogue entry?", "Existing programs keep their copied settings.", function() {
					if ( persist( { version: 1, entries: data.entries.filter( function( old ) { return old.id !== entry.id; } ) } ) ) { editor.empty(); render(); }
				} );
			} );
		}
		$( "<button class='ui-btn'>Cancel</button>" ).appendTo( editor ).on( "click", function() { editor.empty(); } );
		if ( page.hasClass( "ui-page" ) ) { editor.enhanceWithin(); }
	}
	render();
	body.append( "<h2>Catalogue backup</h2><p>Copy this JSON to keep a backup or transfer entries to another browser. Import replaces the catalogue, without changing programs.</p>" );
	var backup = $( "<textarea id='catalog-json' aria-label='Catalogue JSON' rows='8'></textarea>" ).appendTo( body );
	$( "<button id='export-catalog' class='ui-btn'>Export catalogue</button>" ).appendTo( body ).on( "click", function() { backup.val( JSON.stringify( data, null, 2 ) ); } );
	$( "<button id='import-catalog' class='ui-btn'>Import catalogue</button>" ).appendTo( body ).on( "click", function() {
		var next;
		try { next = OSApp.EquipmentCatalog.validate( JSON.parse( backup.val() ) ); } catch ( e ) { OSApp.Errors.showError( e.message ); return; }
		OSApp.UIDom.areYouSure( "Replace this browser’s equipment catalogue?", "Existing programs keep their copied settings.", function() { if ( persist( next ) ) { editor.empty(); render(); } } );
	} );
};
OSApp.EquipmentCatalog.programHelper = function( parent, fields, program ) {
	var entries;
	try { entries = OSApp.EquipmentCatalog.load().entries; } catch ( e ) { parent.append( $( "<p></p>" ).text( e.message ) ); return function() { return program.equipment; }; }
	var snapshot = program.equipment, box = $( "<fieldset data-role='collapsible'><legend>Use equipment catalogue</legend></fieldset>" ).appendTo( parent );
	var select = OSApp.SoilPrograms.select( box, "equipment-choice", "Equipment", [ { value: "", label: "Select equipment" } ].concat( entries.map( function( e ) { return { value: e.id, label: e.name }; } ) ), "" );
	var details = $( "<p></p>" ).appendTo( box ), geometry = {};
	[ [ "rows", "Spacing between runs (metres)" ], [ "count", "Number of emitters" ], [ "length", "Hose length (metres)" ], [ "area", "Represented planting area (m²)" ] ].forEach( function( pair ) {
		geometry[ pair[ 0 ] ] = OSApp.SoilPrograms.field( box, "equipment-" + pair[ 0 ], pair[ 1 ], "", "number" );
	} );
	var preview = $( "<p aria-live='polite'></p>" ).appendTo( box );
	function chosen() { return entries.find( function( e ) { return e.id === select.val(); } ); }
	function values() { var result = {}; Object.keys( geometry ).forEach( function( key ) { result[ key ] = geometry[ key ].val(); } ); return result; }
	function update() {
		var entry = chosen();
		Object.keys( geometry ).forEach( function( key ) { geometry[ key ].closest( ".ui-field-contain" ).toggle( !!entry && ( { dripline: [ "rows" ], emitter: [ "count", "area" ], hose: [ "length", "area" ], rate: [] } )[ entry.type ].includes( key ) ); } );
		details.text( entry ? entry.conditions + " Source: " + entry.source : "" );
		try { preview.text( entry ? "Estimated gross application rate: " + OSApp.EquipmentCatalog.calculate( entry, values() ).toFixed( 3 ) + " mm/hour. Efficiency: " + ( entry.efficiency === "" ? "enter separately" : entry.efficiency + "% (estimate)" ) : "" ); } catch ( e ) { preview.text( e.message ); }
	}
	select.on( "change", update ); box.on( "input change", "input", update ); update();
	var provenance = $( "<p class='small'></p>" ).appendTo( parent );
	if ( snapshot ) {
		try { provenance.text( "Originally estimated from " + JSON.parse( snapshot ).entry.name + ". The editable values above are used for scheduling." ); } catch { provenance.text( "Saved equipment reference is available in the draft export." ); }
	}
	$( "<button id='apply-equipment' type='button' class='ui-btn'>Apply equipment values</button>" ).appendTo( box ).on( "click", function() {
		var entry = chosen();
		try {
			if ( !entry ) { throw new Error( "Select equipment first." ); }
			var rate = OSApp.EquipmentCatalog.calculate( entry, values() );
			fields.rate.val( rate ).trigger( "change" );
			fields.efficiency.val( entry.efficiency ).trigger( "change" );
			snapshot = JSON.stringify( { catalogVersion: 1, entry: entry, geometry: values(), appliedRate: rate } );
			provenance.text( "Estimated from " + entry.name + ". You can override rate and efficiency below." );
		} catch ( e ) { OSApp.Errors.showError( e.message ); }
	} );
	return function() { return snapshot; };
};
