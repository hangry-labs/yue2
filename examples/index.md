---
layout: default
title: Song examples
permalink: /examples/
sidebar: false
wide: true
content_class: song-gallery
stylesheets:
  - /examples/gallery.css
scripts:
  - /examples/catalog.js
  - /examples/player.js
---
{% capture gallery %}{% include_relative index.html %}{% endcapture %}
{{ gallery | split: '<main class="song-gallery">' | last | split: '</main>' | first | strip }}
