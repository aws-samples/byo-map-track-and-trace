# KML → GeoJSON Conversion

This sub-project is responsible for converting KML files (specifically those produced by AutoCAD) to GeoJSON, simplifying and cleaning them up in the process.

## Prerequisites

- `unzip` to decompress KML files.
- `jq` to reformat JSON files.
- [NodeJS](https://nodejs.org/en/) to run JavaScript conversion tools.
- [Python](https://www.python.org/) >= 3.11x to run Python conversion tools.
- [Poetry](https://python-poetry.org/) to manage Python dependencies.

To install JavaScript dependencies, run:

```shell
npm install
```

To install Python dependencies, run:

```shell
poetry install
```

## Usage

```shell
npm run --silent convert <KMZ file> [doc.kml] > <GeoJSON file>
```

(We run the wrapper script with `npm` to set `PATH` so that it includes `togeojson` and `geojson-rewind` (which are in `node_modules/.bin` after installation).)

## Viewing output

Style information (fill and stroke color and opacity) is passed through from AutoCAD via GeoJSON `properties`. The following layer definitions can be used to style a MapLibre overlay.

```javascript
const map = new maplibregl.Map({
  // ...
});

map.addSource("kml", {
  type: "geojson",
  data: "autocad.json",
});

map.addLayer({
  id: "kml-polygons",
  source: "kml",
  type: "fill",
  paint: {
    "fill-color": ["coalesce", ["get", "fill"], "limegreen"],
    "fill-opacity": ["coalesce", ["get", "fill-opacity"], 0],
  },
});

map.addLayer({
  id: "kml-lines",
  source: "kml",
  type: "line",
  paint: {
    "line-color": ["coalesce", ["get", "stroke"], "hotpink"],
    "line-opacity": ["coalesce", ["get", "stroke-opacity"], 0],
  },
});
```

A complete example is available in `public/index.html`; you'll need to update `mapName` (and possibly `region`) to point to an Amazon Location map resource, `apiKey` (with an Amazon Location API key), `center` (and possibly `zoom`) to reflect your data, and `convertedKml` to point at the GeoJSON you created above. Once modified, you can either open `public/index.html` directly or run `npm start` to serve it locally.

## Security

See [../CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This project is licensed under the MIT-0 License. See the LICENSE file.
