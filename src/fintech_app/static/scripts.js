function get(path) {
    var xmlHttp = new XMLHttpRequest();
    xmlHttp.open( "GET", path, false );
    xmlHttp.send( null );
    return xmlHttp;
}
