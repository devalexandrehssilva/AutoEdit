#!/bin/bash
# Remove a restrição do ImageMagick para permitir a criação de textos
sed -i 's/domain="path" rights="none" pattern="@\*"/domain="path" rights="read|write" pattern="@\*"/g' /etc/ImageMagick-6/policy.xml
