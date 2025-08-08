#!/bin/bash

while true; do
    inotifywait -e close_write main.css
    fabric-cli exec lock 'app.set_css()'
done


