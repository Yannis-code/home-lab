<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output method="xml" indent="yes"/>

  <xsl:template match="@*|node()">
    <xsl:copy>
      <xsl:apply-templates select="@*|node()"/>
    </xsl:copy>
  </xsl:template>

  <!-- Force no-secboot firmware loader for HAOS on aarch64 -->
  <xsl:template match="domain/os/loader/text()">/usr/share/AAVMF/AAVMF_CODE.no-secboot.fd</xsl:template>

  <!-- Use non-Microsoft NVRAM template -->
  <xsl:template match="domain/os/nvram/@template">
    <xsl:attribute name="template">/usr/share/AAVMF/AAVMF_VARS.fd</xsl:attribute>
  </xsl:template>

  <!-- Remove secure-boot/enrolled-keys flags injected by default firmware profile -->
  <xsl:template match="domain/os/firmware/feature"/>
</xsl:stylesheet>
