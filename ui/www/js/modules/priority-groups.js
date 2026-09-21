/* global $ */
/* OpenSprinkler App - AGPL-3.0; see ui/LICENSE. */
var OSApp = OSApp || {};
OSApp.PriorityGroups = OSApp.PriorityGroups || {};

// The draft's ordered names remain compatible with existing program assignments.
// Track original names while editing so renames (including swaps) are atomic.
OSApp.PriorityGroups.save = function( baseline, rows ) {
	var data = OSApp.SoilPrograms.load(), names = rows.map( function( row ) { return row.name.trim(); } );
	if ( JSON.stringify( data.groups ) !== JSON.stringify( baseline ) ) {
		throw new Error( "Priority groups changed in another window. Reopen this page before saving." );
	}
	if ( !names.length || names.some( function( name ) { return !name; } ) ) {
		throw new Error( "Keep at least one group and give every group a name." );
	}
	if ( new Set( names.map( function( name ) { return name.toLowerCase(); } ) ).size !== names.length ) {
		throw new Error( "Each priority group needs a unique name." );
	}
	var renamed = new Map();
	rows.forEach( function( row, index ) { if ( row.original !== null ) { renamed.set( row.original, names[ index ] ); } } );
	if ( data.programs.some( function( program ) { return !renamed.has( program.group ); } ) ) {
		throw new Error( "Reassign programs before removing a group they use." );
	}
	data.programs.forEach( function( program ) { program.group = renamed.get( program.group ); } );
	data.groups = names;
	OSApp.SoilPrograms.save( data );
	return data;
};

OSApp.PriorityGroups.displayPage = function() {
	var data, baseline, rows, list, status, nextId = 0;
	function back() { OSApp.UIDom.changePage( "#os-options", { expandItem: "scheduling" } ); }
	function save() {
		if ( !rows ) { return; }
		try {
			data = OSApp.PriorityGroups.save( baseline, rows );
			baseline = data.groups.slice();
			rows.forEach( function( row, index ) { row.name = row.original = baseline[ index ]; } );
			render();
			status.text( "Priority groups saved in this browser." );
		} catch ( e ) { OSApp.Errors.showError( e.message ); }
	}
	var page = OSApp.SoilPrograms.page( "priority-groups", OSApp.Language._( "Priority Groups" ), back, save ), body = page.find( "main" );
	if ( OSApp.currentSession.controller.options.smode !== 1 ) {
		body.append( $( "<p></p>" ).text( "Select and save Soil water balance under Scheduling to manage priority groups." ) );
		return;
	}
	try { data = OSApp.SoilPrograms.load(); } catch ( e ) { body.append( $( "<p></p>" ).text( e.message ) ); return; }
	baseline = data.groups.slice();
	rows = baseline.map( function( name ) { return { id: nextId++, original: name, name: name }; } );
	body.append( $( "<p></p>" ).text( "Highest priority at the top. Use Move up and Move down to set the order, then save. Renaming a group keeps its programs assigned to it." ) );
	list = $( "<div id='priority-group-list'></div>" ).appendTo( body );
	status = $( "<p role='status' aria-live='polite'></p>" ).appendTo( body );
	function render() {
		list.empty();
		rows.forEach( function( row, index ) {
			var card = $( "<fieldset class='priority-group-row'></fieldset>" ).css( { padding: "12px", border: "1px solid #aaa", "border-radius": "5px", "margin-bottom": "12px" } ).appendTo( list );
			$( "<legend></legend>" ).text( index === 0 ? "1 - Highest priority" : String( index + 1 ) ).appendTo( card );
			OSApp.SoilPrograms.field( card, "priority-name-" + row.id, "Group name", row.name ).addClass( "priority-group-name" ).on( "input change", function() {
				row.name = $( this ).val(); status.text( "Unsaved changes." );
			} );
			var actions = $( "<div></div>" ).css( { display: "grid", "grid-template-columns": "repeat(3, minmax(0, 1fr))", gap: "6px" } ).appendTo( card );
			function move( direction ) {
				var target = index + direction;
				if ( target < 0 || target >= rows.length ) { return; }
				rows.splice( index, 1 ); rows.splice( target, 0, row );
				render();
				status.text( ( row.name || "New group" ) + " moved to priority " + ( target + 1 ) + ". Save to apply." );
				list.find( "#priority-name-" + row.id ).trigger( "focus" );
			}
			$( "<button type='button' data-icon='arrow-u' class='ui-btn ui-mini priority-up'>Move up</button>" ).prop( "disabled", index === 0 ).appendTo( actions ).on( "click", function() { move( -1 ); } );
			$( "<button type='button' data-icon='arrow-d' class='ui-btn ui-mini priority-down'>Move down</button>" ).prop( "disabled", index === rows.length - 1 ).appendTo( actions ).on( "click", function() { move( 1 ); } );
			var used = data.programs.some( function( program ) { return program.group === row.original; } );
			$( "<button type='button' class='ui-btn ui-mini priority-remove'>Remove</button>" ).prop( "disabled", used || rows.length === 1 ).appendTo( actions ).on( "click", function() {
				rows.splice( index, 1 ); render(); status.text( "Unsaved changes." );
			} );
			if ( used ) { card.append( $( "<p class='small'></p>" ).text( "Used by a program. Reassign that program before removing this group." ) ); }
		} );
		if ( page.hasClass( "ui-page" ) ) { list.enhanceWithin(); }
	}
	render();
	$( "<button type='button' id='add-priority-group' class='ui-btn'>Add group</button>" ).appendTo( body ).on( "click", function() {
		var row = { id: nextId++, original: null, name: "" };
		rows.push( row ); render(); status.text( "Unsaved changes." ); list.find( "#priority-name-" + row.id ).trigger( "focus" );
	} );
	$( "<button type='button' class='ui-btn ui-btn-b'>Save draft</button>" ).appendTo( body ).on( "click", save );
};
