/* MyPlatoon PPA maps. Maps only reviewed workplace coordinates.
 * The browser requests a location only after an explicit button click.
 * All external text is inserted as textContent to avoid popup injection.
 */
(function () {
  "use strict";
  if (!window.L) return;
  const listEl = document.getElementById("ppa-map");
  const pickerEl = document.getElementById("ppa-location-picker");
  if (!listEl && !pickerEl) return;

  const map = L.map(listEl || pickerEl).setView([9.08, 8.67], 6);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'
  }).addTo(map);
  const markers = L.featureGroup().addTo(map);
  const latField = document.getElementById(listEl ? "ppa-lat" : "latitude");
  const lngField = document.getElementById(listEl ? "ppa-lng" : "longitude");
  const statusEl = document.getElementById("ppa-map-status");
  let originMarker;

  function choosePin(lat, lng) {
    if (!latField || !lngField) return;
    latField.value = Number(lat).toFixed(6);
    lngField.value = Number(lng).toFixed(6);
    if (originMarker) map.removeLayer(originMarker);
    originMarker = L.circleMarker([lat, lng], {
      radius: 9, color: "#8d5316", fillColor: "#e6aa4a", fillOpacity: .9
    }).addTo(map);
    if (statusEl) statusEl.textContent =
      "Selected " + latField.value + ", " + lngField.value +
      ". Tap Search to find PPAs within your chosen radius.";
  }

  map.on("click", function (event) {
    choosePin(event.latlng.lat, event.latlng.lng);
  });

  if (latField && lngField && latField.value && lngField.value) {
    const la = Number(latField.value);
    const lo = Number(lngField.value);
    if (Number.isFinite(la) && Number.isFinite(lo) &&
        la >= -90 && la <= 90 && lo >= -180 && lo <= 180) {
      choosePin(la, lo);
      map.setView([la, lo], 12);
    }
  }

  if (listEl) {
    const query = new URLSearchParams(window.location.search);
    fetch("/ppas/geojson?" + query.toString(), { credentials: "same-origin" })
      .then(function (r) { if (!r.ok) throw Error("Map data unavailable"); return r.json(); })
      .then(function (data) {
        const features = Array.isArray(data.features) ? data.features : [];
        features.forEach(function (feature) {
          if (!feature || !feature.geometry || feature.geometry.type !== "Point") return;
          const xy = feature.geometry.coordinates;
          if (!Array.isArray(xy) || xy.length !== 2) return;
          const lon = Number(xy[0]), lat = Number(xy[1]);
          if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
          const p = feature.properties || {};
          const marker = L.marker([lat, lon]).addTo(markers);
          const popup = document.createElement("div");
          const title = document.createElement("strong");
          title.textContent = p.name || "PPA";
          const location = document.createElement("p");
          location.className = "mb-1";
          location.textContent = [p.lga, p.state].filter(Boolean).join(", ");
          const link = document.createElement("a");
          link.href = "/ppas/" + encodeURIComponent(String(p.id || ""));
          link.textContent = "View PPA details";
          popup.appendChild(title);
          popup.appendChild(location);
          popup.appendChild(link);
          marker.bindPopup(popup);
        });
        if (markers.getLayers().length && !(latField && latField.value)) {
          map.fitBounds(markers.getBounds().pad(.15), { maxZoom: 12 });
        }
        if (data.truncated && statusEl) {
          statusEl.textContent = "Showing the first 250 mapped PPAs. Narrow your state or sector to see more.";
        }
      })
      .catch(function () {
        if (statusEl) statusEl.textContent =
          "Map pins could not load. You can still use the PPA list and filters.";
      });

    const button = document.getElementById("ppa-use-location");
    if (button) button.addEventListener("click", function () {
      if (!navigator.geolocation) {
        if (statusEl) statusEl.textContent = "Your browser does not offer location sharing.";
        return;
      }
      button.disabled = true;
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          choosePin(pos.coords.latitude, pos.coords.longitude);
          map.setView([pos.coords.latitude, pos.coords.longitude], 12);
          button.disabled = false;
        },
        function () {
          if (statusEl) statusEl.textContent =
            "Location was not shared. Tap a point on the map instead.";
          button.disabled = false;
        },
        { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 }
      );
    });
  }
})();
