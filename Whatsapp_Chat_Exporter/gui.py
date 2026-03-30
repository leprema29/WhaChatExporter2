"""
Web-based GUI for WhatsApp Chat Exporter.
Provides a local Flask web interface for configuring and running exports.
Launch with: wtsexporter-gui or python -m Whatsapp_Chat_Exporter.gui
"""

import os
import sys
import json
import logging
import threading
import webbrowser
from datetime import datetime
from io import StringIO
from typing import Optional

try:
    from flask import Flask, render_template_string, request, jsonify, send_from_directory
except ImportError:
    Flask = None

# HTML template for the GUI
GUI_TEMPLATE = r'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WhatsApp Chat Exporter</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        whatsapp: {
                            light: '#e7ffdb',
                            DEFAULT: '#25D366',
                            dark: '#075E54',
                            darker: '#054d44',
                            chat: '#efeae2',
                        }
                    }
                }
            }
        }
    </script>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
        .tab-active { border-bottom: 3px solid #25D366; color: #075E54; font-weight: 600; }
        .tab-inactive { border-bottom: 3px solid transparent; color: #667781; }
        .tab-inactive:hover { color: #075E54; }
        .log-output { font-family: 'Fira Code', 'Consolas', monospace; font-size: 12px; }
        .fade-in { animation: fadeIn 0.3s ease-in; }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        input[type="file"]::file-selector-button {
            background-color: #25D366;
            color: white;
            border: none;
            padding: 6px 16px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
        }
        input[type="file"]::file-selector-button:hover { background-color: #075E54; }
        .toggle-switch { position: relative; display: inline-block; width: 44px; height: 24px; }
        .toggle-switch input { opacity: 0; width: 0; height: 0; }
        .toggle-slider { position: absolute; cursor: pointer; inset: 0; background: #ccc; border-radius: 24px; transition: 0.3s; }
        .toggle-slider:before { content: ""; position: absolute; height: 18px; width: 18px; left: 3px; bottom: 3px; background: white; border-radius: 50%; transition: 0.3s; }
        input:checked + .toggle-slider { background: #25D366; }
        input:checked + .toggle-slider:before { transform: translateX(20px); }
    </style>
</head>
<body class="bg-gray-50 min-h-screen">
    <!-- Header -->
    <header class="bg-whatsapp-dark text-white shadow-lg">
        <div class="max-w-5xl mx-auto px-6 py-4">
            <div class="flex items-center justify-between">
                <div>
                    <h1 class="text-2xl font-bold tracking-tight">WhatsApp Chat Exporter</h1>
                    <p class="text-sm text-green-200 mt-0.5">Local Web Interface</p>
                </div>
                <div class="flex items-center gap-3">
                    <span id="statusBadge" class="px-3 py-1 rounded-full text-xs font-medium bg-green-400/20 text-green-200">
                        Ready
                    </span>
                </div>
            </div>
        </div>
    </header>

    <main class="max-w-5xl mx-auto px-6 py-8">
        <!-- Tabs -->
        <div class="flex gap-6 border-b border-gray-200 mb-8">
            <button onclick="showTab('config')" id="tab-config" class="tab-active pb-3 px-1 text-sm transition-all">
                Configuration
            </button>
            <button onclick="showTab('connected')" id="tab-connected" class="tab-inactive pb-3 px-1 text-sm transition-all">
                Connected Mode
            </button>
            <button onclick="showTab('compare')" id="tab-compare" class="tab-inactive pb-3 px-1 text-sm transition-all">
                Compare DBs
            </button>
            <button onclick="showTab('output')" id="tab-output" class="tab-inactive pb-3 px-1 text-sm transition-all">
                Output & Logs
            </button>
        </div>

        <!-- Config Tab -->
        <div id="panel-config" class="fade-in">
            <form id="exportForm" class="space-y-8">
                <!-- Device Selection -->
                <section class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                    <h2 class="text-lg font-semibold text-gray-800 mb-4">Device Type</h2>
                    <div class="grid grid-cols-3 gap-4">
                        <label class="relative cursor-pointer">
                            <input type="radio" name="device" value="android" class="peer sr-only" checked>
                            <div class="p-4 rounded-lg border-2 border-gray-200 peer-checked:border-whatsapp peer-checked:bg-whatsapp/5 text-center transition-all">
                                <div class="text-2xl mb-1">&#x1f4f1;</div>
                                <span class="text-sm font-medium">Android</span>
                            </div>
                        </label>
                        <label class="relative cursor-pointer">
                            <input type="radio" name="device" value="ios" class="peer sr-only">
                            <div class="p-4 rounded-lg border-2 border-gray-200 peer-checked:border-whatsapp peer-checked:bg-whatsapp/5 text-center transition-all">
                                <div class="text-2xl mb-1">&#x1f34e;</div>
                                <span class="text-sm font-medium">iOS</span>
                            </div>
                        </label>
                        <label class="relative cursor-pointer">
                            <input type="radio" name="device" value="exported" class="peer sr-only">
                            <div class="p-4 rounded-lg border-2 border-gray-200 peer-checked:border-whatsapp peer-checked:bg-whatsapp/5 text-center transition-all">
                                <div class="text-2xl mb-1">&#x1f4c4;</div>
                                <span class="text-sm font-medium">Exported Chat</span>
                            </div>
                        </label>
                    </div>
                </section>

                <!-- Input Files -->
                <section class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                    <h2 class="text-lg font-semibold text-gray-800 mb-4">Input Files</h2>
                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-600 mb-1">Message Database</label>
                            <input type="text" name="db" placeholder="msgstore.db"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-whatsapp/30 focus:border-whatsapp outline-none">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-600 mb-1">Contact Database</label>
                            <input type="text" name="wa" placeholder="wa.db"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-whatsapp/30 focus:border-whatsapp outline-none">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-600 mb-1">Media Folder</label>
                            <input type="text" name="media" placeholder="WhatsApp"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-whatsapp/30 focus:border-whatsapp outline-none">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-600 mb-1">Backup File (for encrypted)</label>
                            <input type="text" name="backup" placeholder=""
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-whatsapp/30 focus:border-whatsapp outline-none">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-600 mb-1">Key (file path or 64 hex chars)</label>
                            <input type="text" name="key" placeholder="path/to/key OR a1b2c3d4..."
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-whatsapp/30 focus:border-whatsapp outline-none">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-600 mb-1">Key Screenshot (OCR extraction)</label>
                            <input type="text" name="key_image" placeholder="path/to/screenshot.png"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-whatsapp/30 focus:border-whatsapp outline-none">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-600 mb-1">Exported Chat File</label>
                            <input type="text" name="exported_file" placeholder="chat.txt"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-whatsapp/30 focus:border-whatsapp outline-none">
                        </div>
                    </div>
                </section>

                <!-- Output Options -->
                <section class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                    <h2 class="text-lg font-semibold text-gray-800 mb-4">Output Options</h2>
                    <div class="grid grid-cols-2 gap-4 mb-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-600 mb-1">Output Directory</label>
                            <input type="text" name="output" value="result"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-whatsapp/30 focus:border-whatsapp outline-none">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-600 mb-1">Timezone Offset</label>
                            <input type="number" name="timezone_offset" value="0" min="-12" max="14"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-whatsapp/30 focus:border-whatsapp outline-none">
                        </div>
                    </div>
                    <h3 class="text-sm font-semibold text-gray-700 mb-3">Export Formats</h3>
                    <div class="grid grid-cols-3 md:grid-cols-6 gap-3">
                        <label class="flex items-center gap-2 cursor-pointer">
                            <div class="toggle-switch">
                                <input type="checkbox" name="html" checked>
                                <span class="toggle-slider"></span>
                            </div>
                            <span class="text-sm">HTML</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <div class="toggle-switch">
                                <input type="checkbox" name="json_export">
                                <span class="toggle-slider"></span>
                            </div>
                            <span class="text-sm">JSON</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <div class="toggle-switch">
                                <input type="checkbox" name="txt">
                                <span class="toggle-slider"></span>
                            </div>
                            <span class="text-sm">TXT</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <div class="toggle-switch">
                                <input type="checkbox" name="pdf">
                                <span class="toggle-slider"></span>
                            </div>
                            <span class="text-sm">PDF</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <div class="toggle-switch">
                                <input type="checkbox" name="markdown">
                                <span class="toggle-slider"></span>
                            </div>
                            <span class="text-sm">Markdown</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <div class="toggle-switch">
                                <input type="checkbox" name="csv">
                                <span class="toggle-slider"></span>
                            </div>
                            <span class="text-sm">CSV</span>
                        </label>
                    </div>
                </section>

                <!-- Advanced Options -->
                <section class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                    <h2 class="text-lg font-semibold text-gray-800 mb-4">Advanced Options</h2>
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <label class="flex items-center gap-2 cursor-pointer">
                            <div class="toggle-switch">
                                <input type="checkbox" name="overview">
                                <span class="toggle-slider"></span>
                            </div>
                            <span class="text-sm">Overview Page</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <div class="toggle-switch">
                                <input type="checkbox" name="anonymize">
                                <span class="toggle-slider"></span>
                            </div>
                            <span class="text-sm">Anonymize</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <div class="toggle-switch">
                                <input type="checkbox" name="no_avatar">
                                <span class="toggle-slider"></span>
                            </div>
                            <span class="text-sm">No Avatars</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <div class="toggle-switch">
                                <input type="checkbox" name="old_theme">
                                <span class="toggle-slider"></span>
                            </div>
                            <span class="text-sm">Old Theme</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <div class="toggle-switch">
                                <input type="checkbox" name="move_media">
                                <span class="toggle-slider"></span>
                            </div>
                            <span class="text-sm">Move Media</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <div class="toggle-switch">
                                <input type="checkbox" name="separate_media">
                                <span class="toggle-slider"></span>
                            </div>
                            <span class="text-sm">Separate Media</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <div class="toggle-switch">
                                <input type="checkbox" name="business">
                                <span class="toggle-slider"></span>
                            </div>
                            <span class="text-sm">Business</span>
                        </label>
                        <label class="flex items-center gap-2 cursor-pointer">
                            <div class="toggle-switch">
                                <input type="checkbox" name="fix_dot_files">
                                <span class="toggle-slider"></span>
                            </div>
                            <span class="text-sm">Fix Dot Files</span>
                        </label>
                    </div>
                    <div class="grid grid-cols-2 gap-4 mt-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-600 mb-1">Filter by Chat Name</label>
                            <input type="text" name="chat_name" placeholder="e.g. Family, Work (comma-separated)"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-whatsapp/30 focus:border-whatsapp outline-none">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-600 mb-1">Date Filter</label>
                            <input type="text" name="date_filter" placeholder="e.g. > 2024-01-01 00:00"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-whatsapp/30 focus:border-whatsapp outline-none">
                        </div>
                    </div>
                </section>

                <!-- Chat Selection -->
                <section id="chatSelectionSection" class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 hidden">
                    <div class="flex items-center justify-between mb-4">
                        <h2 class="text-lg font-semibold text-gray-800">Select Chats to Export</h2>
                        <div class="flex gap-2">
                            <button type="button" onclick="toggleAllChats(true)" class="px-3 py-1 text-xs bg-whatsapp text-white rounded-lg">Select All</button>
                            <button type="button" onclick="toggleAllChats(false)" class="px-3 py-1 text-xs border border-gray-300 rounded-lg">Deselect All</button>
                        </div>
                    </div>
                    <input type="text" id="chatSearchInput" placeholder="Search chats..."
                           class="w-full px-3 py-2 mb-3 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-whatsapp/30 focus:border-whatsapp outline-none"
                           oninput="filterChatList()">
                    <div id="chatListContainer" class="max-h-80 overflow-y-auto border border-gray-200 rounded-lg">
                        <p class="p-4 text-gray-400 text-sm">Click "Scan Chats" to load available conversations...</p>
                    </div>
                    <p id="chatSelectionCount" class="text-xs text-gray-500 mt-2"></p>
                </section>

                <!-- Submit -->
                <div class="flex justify-end gap-4">
                    <button type="button" onclick="scanChats()" id="scanBtn"
                            class="px-6 py-2.5 border-2 border-whatsapp text-whatsapp rounded-lg text-sm font-medium hover:bg-whatsapp/5 transition-colors">
                        Scan Chats
                    </button>
                    <button type="button" onclick="generateCommand()"
                            class="px-6 py-2.5 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors">
                        Show Command
                    </button>
                    <button type="submit" id="exportBtn"
                            class="px-8 py-2.5 bg-whatsapp text-white rounded-lg text-sm font-semibold hover:bg-whatsapp-dark transition-colors shadow-sm">
                        Start Export
                    </button>
                </div>
            </form>
        </div>

        <!-- Connected Mode Tab -->
        <div id="panel-connected" class="hidden fade-in">
            <div class="space-y-6">
                <!-- Guide -->
                <section class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                    <h2 class="text-lg font-semibold text-gray-800 mb-2">How to Get Your Encryption Key</h2>
                    <p class="text-sm text-gray-500 mb-4">One key decrypts ALL crypt15 backups from the same account. The key only changes if you reinstall WhatsApp.</p>

                    <div class="space-y-4">
                        <!-- Method 1 -->
                        <div class="border border-green-200 rounded-lg p-4 bg-green-50/50">
                            <h3 class="font-semibold text-green-800 text-sm mb-2">Method 1: From WhatsApp Settings (easiest)</h3>
                            <ol class="text-sm text-gray-700 space-y-1 list-decimal list-inside">
                                <li>Open <b>WhatsApp</b> on your phone</li>
                                <li>Go to <b>Settings &gt; Chats &gt; Chat Backup</b></li>
                                <li>Tap <b>"End-to-end Encrypted Backup"</b></li>
                                <li>Your <b>64-character key</b> is displayed</li>
                                <li>Take a <b>screenshot</b> or copy the characters</li>
                            </ol>
                        </div>

                        <!-- Method 2 -->
                        <div class="border border-blue-200 rounded-lg p-4 bg-blue-50/50">
                            <h3 class="font-semibold text-blue-800 text-sm mb-2">Method 2: From key file (rooted Android)</h3>
                            <p class="text-sm text-gray-700">The key file is at: <code class="bg-gray-100 px-1 rounded text-xs">/data/data/com.whatsapp/files/encrypted_backup.key</code></p>
                            <p class="text-sm text-gray-700 mt-1">Copy it to your PC with ADB, then provide the path below.</p>
                        </div>

                        <!-- Method 3 -->
                        <div class="border border-purple-200 rounded-lg p-4 bg-purple-50/50">
                            <h3 class="font-semibold text-purple-800 text-sm mb-2">Method 3: Using wa-crypt-tools</h3>
                            <p class="text-sm text-gray-700"><code class="bg-gray-100 px-1 rounded text-xs">pip install wa-crypt-tools</code> then follow its docs.</p>
                        </div>

                        <!-- Method 4: Emulator -->
                        <div class="border border-orange-200 rounded-lg p-4 bg-orange-50/50">
                            <h3 class="font-semibold text-orange-800 text-sm mb-2">Method 4: Android Emulator (if no access to phone)</h3>
                            <ol class="text-sm text-gray-700 space-y-1 list-decimal list-inside">
                                <li>Install <a href="https://www.genymotion.com/download/" class="text-blue-600 underline" target="_blank">Genymotion</a> (free for personal use)</li>
                                <li>Create an Android 11+ device with <b>Google Play</b> (or use BlueStacks)</li>
                                <li>Install <b>WhatsApp</b> from Play Store in the emulator</li>
                                <li>Register with your phone number (SMS will go to your real phone)</li>
                                <li>Once WhatsApp is set up, click <b>"Extract Key from Emulator"</b> below</li>
                            </ol>
                            <p class="text-xs text-orange-600 mt-2">The emulator is rooted by default so we can extract the key directly.</p>
                        </div>
                    </div>
                </section>

                <!-- Emulator Extraction -->
                <section class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                    <h2 class="text-lg font-semibold text-gray-800 mb-4">Emulator / ADB Extraction</h2>
                    <p class="text-sm text-gray-500 mb-4">Detects connected Android devices and emulators, checks WhatsApp status, and extracts the key automatically.</p>

                    <div class="flex gap-3 mb-4">
                        <button type="button" onclick="checkAdbDevices()"
                                class="px-5 py-2 bg-orange-500 text-white rounded-lg text-sm font-semibold hover:bg-orange-600 transition-colors">
                            1. Check Connected Devices
                        </button>
                        <button type="button" onclick="extractFromAdb()" id="extractAdbBtn" disabled
                                class="px-5 py-2 bg-whatsapp text-white rounded-lg text-sm font-semibold hover:bg-whatsapp-dark transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
                            2. Extract Key
                        </button>
                    </div>
                    <div id="adbStatus" class="text-sm text-gray-600"></div>
                </section>

                <!-- Key Input -->
                <section class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                    <h2 class="text-lg font-semibold text-gray-800 mb-4">Enter Your Key</h2>
                    <div class="space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-600 mb-1">Paste 64 hex characters (with or without spaces)</label>
                            <textarea id="connKeyInput" rows="3" placeholder="e.g. a1 b2 c3 d4 e5 f6 ... (64 hex characters)"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-whatsapp/30 focus:border-whatsapp outline-none"></textarea>
                        </div>
                        <div class="text-center text-gray-400 text-xs">- OR -</div>
                        <div>
                            <label class="block text-sm font-medium text-gray-600 mb-1">Key file path</label>
                            <input type="text" id="connKeyFile" placeholder="C:\path\to\encrypted_backup.key"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-whatsapp/30 focus:border-whatsapp outline-none">
                        </div>
                        <div class="text-center text-gray-400 text-xs">- OR -</div>
                        <div>
                            <label class="block text-sm font-medium text-gray-600 mb-1">Screenshot of the key (OCR extraction)</label>
                            <input type="text" id="connKeyScreenshot" placeholder="C:\path\to\screenshot.png"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-whatsapp/30 focus:border-whatsapp outline-none">
                        </div>

                        <div class="flex gap-3">
                            <button type="button" onclick="validateAndUseKey()"
                                    class="px-6 py-2.5 bg-whatsapp text-white rounded-lg text-sm font-semibold hover:bg-whatsapp-dark transition-colors">
                                Validate & Use Key
                            </button>
                            <button type="button" onclick="extractFromAdb()"
                                    class="px-6 py-2.5 border border-gray-300 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50 transition-colors">
                                Extract via ADB
                            </button>
                        </div>

                        <div id="connResult" class="hidden mt-4 p-4 bg-green-50 border border-green-200 rounded-lg">
                            <p class="text-sm font-medium text-green-800">Key validated successfully!</p>
                            <code id="connKey" class="block mt-2 p-2 bg-white rounded border text-xs font-mono break-all"></code>
                            <button type="button" onclick="useRetrievedKey()" class="mt-3 px-4 py-2 bg-whatsapp text-white rounded-lg text-sm hover:bg-whatsapp-dark">
                                Use This Key for Export
                            </button>
                        </div>

                        <div id="connError" class="hidden mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
                            <p class="text-sm text-red-700" id="connErrorMsg"></p>
                        </div>
                    </div>
                </section>
            </div>
        </div>

        <!-- Compare DBs Tab -->
        <div id="panel-compare" class="hidden fade-in">
            <div class="space-y-6">
                <section class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
                    <h2 class="text-lg font-semibold text-gray-800 mb-2">Compare Databases - Find Deleted Messages</h2>
                    <p class="text-sm text-gray-500 mb-6">Provide multiple msgstore.db files (already decrypted) from different dates. The tool will compare them to find messages that were deleted.</p>

                    <div class="space-y-4">
                        <div id="dbInputs">
                            <div class="flex gap-2 mb-2 db-input-row">
                                <input type="text" placeholder="Path to first msgstore.db (oldest)" class="compare-db flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-whatsapp/30 focus:border-whatsapp outline-none">
                                <span class="text-xs text-gray-400 self-center w-16">Oldest</span>
                            </div>
                            <div class="flex gap-2 mb-2 db-input-row">
                                <input type="text" placeholder="Path to second msgstore.db (newest)" class="compare-db flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-whatsapp/30 focus:border-whatsapp outline-none">
                                <span class="text-xs text-gray-400 self-center w-16">Newest</span>
                            </div>
                        </div>
                        <button type="button" onclick="addDbInput()" class="text-sm text-whatsapp hover:underline">+ Add another database</button>

                        <div class="flex gap-3 mt-4">
                            <button type="button" onclick="runComparison()" id="compareBtn"
                                    class="px-6 py-2.5 bg-whatsapp text-white rounded-lg text-sm font-semibold hover:bg-whatsapp-dark transition-colors">
                                Compare & Find Deleted Messages
                            </button>
                        </div>

                        <div id="compareResult" class="hidden mt-4"></div>
                    </div>
                </section>
            </div>
        </div>

        <!-- Output Tab -->
        <div id="panel-output" class="hidden fade-in">
            <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
                <div class="bg-gray-800 text-gray-100 p-4 min-h-[500px] max-h-[600px] overflow-y-auto log-output" id="logOutput">
                    <p class="text-gray-500">Export logs will appear here...</p>
                </div>
            </div>
            <div class="mt-4 flex justify-between items-center">
                <div id="progressInfo" class="text-sm text-gray-500"></div>
                <button onclick="clearLogs()" class="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">Clear Logs</button>
            </div>
        </div>

        <!-- Command Modal -->
        <div id="commandModal" class="hidden fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div class="bg-white rounded-xl shadow-xl p-6 max-w-2xl w-full mx-4">
                <h3 class="text-lg font-semibold mb-3">CLI Command</h3>
                <pre id="commandOutput" class="bg-gray-800 text-green-400 p-4 rounded-lg text-sm overflow-x-auto"></pre>
                <div class="flex justify-end mt-4 gap-3">
                    <button onclick="copyCommand()" class="px-4 py-2 text-sm bg-whatsapp text-white rounded-lg hover:bg-whatsapp-dark">
                        Copy
                    </button>
                    <button onclick="document.getElementById('commandModal').classList.add('hidden')"
                            class="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">
                        Close
                    </button>
                </div>
            </div>
        </div>
    </main>

    <script>
    function showTab(name) {
        document.querySelectorAll('[id^="panel-"]').forEach(p => p.classList.add('hidden'));
        document.querySelectorAll('[id^="tab-"]').forEach(t => { t.className = 'tab-inactive pb-3 px-1 text-sm transition-all'; });
        document.getElementById('panel-' + name).classList.remove('hidden');
        document.getElementById('tab-' + name).className = 'tab-active pb-3 px-1 text-sm transition-all';
    }

    function getFormData() {
        const form = document.getElementById('exportForm');
        const data = {};
        const formData = new FormData(form);
        for (const [key, value] of formData.entries()) {
            data[key] = value;
        }
        // Handle checkboxes explicitly
        ['html', 'json_export', 'txt', 'pdf', 'markdown', 'csv', 'overview',
         'anonymize', 'no_avatar', 'old_theme', 'move_media', 'separate_media',
         'business', 'fix_dot_files'].forEach(name => {
            const el = form.querySelector(`[name="${name}"]`);
            if (el) data[name] = el.checked;
        });
        return data;
    }

    function buildArgs(data) {
        const args = ['wtsexporter'];
        if (data.device === 'android') args.push('-a');
        else if (data.device === 'ios') args.push('-i');
        else if (data.device === 'exported') { args.push('-e'); if (data.exported_file) args.push(data.exported_file); }
        if (data.db) { args.push('-d'); args.push(data.db); }
        if (data.wa) { args.push('-w'); args.push(data.wa); }
        if (data.media) { args.push('-m'); args.push(data.media); }
        if (data.backup) { args.push('-b'); args.push(data.backup); }
        if (data.key) { args.push('-k'); args.push(data.key); }
        if (data.output && data.output !== 'result') { args.push('-o'); args.push(data.output); }
        if (data.timezone_offset && data.timezone_offset !== '0') { args.push('--time-offset'); args.push(data.timezone_offset); }
        if (!data.html) args.push('--no-html');
        if (data.json_export) args.push('-j');
        if (data.txt) args.push('--txt');
        if (data.pdf) args.push('--pdf');
        if (data.markdown) args.push('--markdown');
        if (data.csv) args.push('--csv');
        if (data.overview) args.push('--overview');
        if (data.anonymize) args.push('--anonymize');
        if (data.no_avatar) args.push('--no-avatar');
        if (data.old_theme) args.push('--old-theme');
        if (data.move_media) args.push('-c');
        if (data.separate_media) args.push('--create-separated-media');
        if (data.business) args.push('--business');
        if (data.fix_dot_files) args.push('--fix-dot-files');
        if (data.chat_name) { data.chat_name.split(',').map(s => s.trim()).filter(Boolean).forEach(n => { args.push('--chat-name'); args.push(n); }); }
        if (data.date_filter) { args.push('--date'); args.push(data.date_filter); }
        // Selected chats (via phone number include filter)
        if (data.selected_chats && data.selected_chats.length > 0) {
            data.selected_chats.forEach(jid => {
                const phone = jid.split('@')[0];
                if (phone) { args.push('--include'); args.push(phone); }
            });
        }
        return args;
    }

    function generateCommand() {
        const data = getFormData();
        const args = buildArgs(data);
        document.getElementById('commandOutput').textContent = args.join(' ');
        document.getElementById('commandModal').classList.remove('hidden');
    }

    function copyCommand() {
        const text = document.getElementById('commandOutput').textContent;
        navigator.clipboard.writeText(text);
    }

    // Chat scanning and selection
    async function scanChats() {
        const data = getFormData();
        const btn = document.getElementById('scanBtn');
        btn.disabled = true;
        btn.textContent = 'Scanning...';

        try {
            const response = await fetch('/api/list-chats', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const result = await response.json();

            if (result.error) {
                alert('Error: ' + result.error);
                return;
            }

            const container = document.getElementById('chatListContainer');
            container.innerHTML = '';

            result.chats.forEach((chat, i) => {
                const div = document.createElement('div');
                div.className = 'flex items-center gap-3 p-3 border-b border-gray-100 hover:bg-gray-50 chat-item';
                div.dataset.name = (chat.name || '').toLowerCase();
                div.innerHTML = `
                    <input type="checkbox" checked class="chat-checkbox w-4 h-4 text-whatsapp rounded focus:ring-whatsapp"
                           value="${chat.jid}" id="chat-${i}">
                    <label for="chat-${i}" class="flex-1 cursor-pointer">
                        <span class="font-medium text-sm text-gray-800">${chat.name || chat.jid}</span>
                        <span class="text-xs text-gray-400 ml-2">${chat.message_count} messages</span>
                    </label>
                `;
                container.appendChild(div);
            });

            document.getElementById('chatSelectionSection').classList.remove('hidden');
            updateChatCount();
        } catch (err) {
            alert('Error scanning chats: ' + err.message);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Scan Chats';
        }
    }

    function toggleAllChats(checked) {
        document.querySelectorAll('.chat-checkbox').forEach(cb => cb.checked = checked);
        updateChatCount();
    }

    function filterChatList() {
        const search = document.getElementById('chatSearchInput').value.toLowerCase();
        document.querySelectorAll('.chat-item').forEach(item => {
            item.style.display = item.dataset.name.includes(search) ? '' : 'none';
        });
    }

    function updateChatCount() {
        const total = document.querySelectorAll('.chat-checkbox').length;
        const selected = document.querySelectorAll('.chat-checkbox:checked').length;
        document.getElementById('chatSelectionCount').textContent = `${selected} / ${total} chats selected`;
    }

    // Observe checkbox changes
    document.addEventListener('change', function(e) {
        if (e.target.classList.contains('chat-checkbox')) updateChatCount();
    });

    function getSelectedChats() {
        const checkboxes = document.querySelectorAll('.chat-checkbox:checked');
        if (checkboxes.length === 0) return [];
        const allCheckboxes = document.querySelectorAll('.chat-checkbox');
        if (checkboxes.length === allCheckboxes.length) return []; // All selected = no filter
        return Array.from(checkboxes).map(cb => cb.value);
    }

    function clearLogs() {
        document.getElementById('logOutput').innerHTML = '<p class="text-gray-500">Export logs will appear here...</p>';
    }

    function appendLog(message, type) {
        const log = document.getElementById('logOutput');
        if (log.querySelector('.text-gray-500')) log.innerHTML = '';
        const line = document.createElement('div');
        line.className = type === 'error' ? 'text-red-400' : type === 'warning' ? 'text-yellow-400' : 'text-gray-300';
        line.textContent = message;
        log.appendChild(line);
        log.scrollTop = log.scrollHeight;
    }

    // Connected mode handlers
    async function validateAndUseKey() {
        const keyInput = document.getElementById('connKeyInput').value.trim();
        const keyFile = document.getElementById('connKeyFile').value.trim();
        const keyScreenshot = document.getElementById('connKeyScreenshot').value.trim();
        document.getElementById('connError').classList.add('hidden');
        document.getElementById('connResult').classList.add('hidden');

        const payload = {};
        if (keyInput) payload.key_hex = keyInput;
        else if (keyFile) payload.key_file = keyFile;
        else if (keyScreenshot) payload.key_image = keyScreenshot;
        else { alert('Enter a key, file path, or screenshot path'); return; }

        try {
            const resp = await fetch('/api/connected/validate-key', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            const result = await resp.json();
            if (result.error) {
                document.getElementById('connErrorMsg').textContent = result.error;
                document.getElementById('connError').classList.remove('hidden');
            } else if (result.key) {
                document.getElementById('connKey').textContent = result.key;
                document.getElementById('connResult').classList.remove('hidden');
            }
        } catch(e) {
            document.getElementById('connErrorMsg').textContent = e.message;
            document.getElementById('connError').classList.remove('hidden');
        }
    }

    async function checkAdbDevices() {
        const statusDiv = document.getElementById('adbStatus');
        statusDiv.innerHTML = '<p class="text-gray-400">Checking devices...</p>';
        try {
            const resp = await fetch('/api/connected/adb-status', { method: 'POST' });
            const result = await resp.json();
            if (!result.available) {
                statusDiv.innerHTML = `<div class="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">${result.error || 'ADB not available'}<br><br>Install <a href="https://developer.android.com/tools/releases/platform-tools" class="underline" target="_blank">Android Platform Tools</a> and add to PATH.</div>`;
                return;
            }
            if (result.devices.length === 0) {
                statusDiv.innerHTML = '<div class="p-3 bg-yellow-50 border border-yellow-200 rounded-lg text-sm text-yellow-700">No devices found. Make sure your emulator is running or phone is connected with USB debugging enabled.</div>';
                return;
            }
            let html = '<div class="space-y-2">';
            for (const dev of result.devices) {
                const model = dev.model || dev.type || 'unknown';
                const waStatus = dev.whatsapp_installed ?
                    `<span class="text-green-600">WhatsApp installed${dev.has_key ? ' (key found!)' : ''}</span>` :
                    '<span class="text-red-600">WhatsApp not installed</span>';
                const rootStatus = dev.is_root ? '<span class="text-green-600">rooted</span>' : '<span class="text-yellow-600">not rooted</span>';
                html += `<div class="p-3 bg-gray-50 border rounded-lg flex justify-between items-center">
                    <div><b>${dev.serial}</b> (${model}) - ${rootStatus} - ${waStatus}</div>
                </div>`;
            }
            html += '</div>';
            statusDiv.innerHTML = html;
            document.getElementById('extractAdbBtn').disabled = false;
        } catch(e) {
            statusDiv.innerHTML = `<div class="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">${e.message}</div>`;
        }
    }

    async function extractFromAdb() {
        document.getElementById('connError').classList.add('hidden');
        document.getElementById('connResult').classList.add('hidden');
        const statusDiv = document.getElementById('adbStatus');
        statusDiv.innerHTML += '<p class="text-gray-400 mt-2">Extracting key...</p>';
        try {
            const resp = await fetch('/api/connected/adb-extract', { method: 'POST' });
            const result = await resp.json();
            if (result.error) {
                document.getElementById('connErrorMsg').textContent = result.error;
                document.getElementById('connError').classList.remove('hidden');
            } else if (result.key) {
                document.getElementById('connKey').textContent = result.key;
                document.getElementById('connResult').classList.remove('hidden');
                statusDiv.innerHTML += '<p class="text-green-600 mt-2 font-semibold">Key extracted successfully!</p>';
            }
        } catch(e) {
            document.getElementById('connErrorMsg').textContent = e.message;
            document.getElementById('connError').classList.remove('hidden');
        }
    }

    function useRetrievedKey() {
        const key = document.getElementById('connKey').textContent;
        document.querySelector('input[name="key"]').value = key;
        showTab('config');
    }

    // Compare DBs handlers
    function addDbInput() {
        const container = document.getElementById('dbInputs');
        const count = container.querySelectorAll('.db-input-row').length + 1;
        const div = document.createElement('div');
        div.className = 'flex gap-2 mb-2 db-input-row';
        div.innerHTML = `<input type="text" placeholder="Path to msgstore.db #${count}" class="compare-db flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-whatsapp/30 focus:border-whatsapp outline-none">
            <button type="button" onclick="this.parentElement.remove()" class="text-red-400 hover:text-red-600 text-sm px-2">Remove</button>`;
        container.appendChild(div);
    }

    async function runComparison() {
        const inputs = document.querySelectorAll('.compare-db');
        const dbs = Array.from(inputs).map(i => i.value.trim()).filter(Boolean);
        if (dbs.length < 2) { alert('You need at least 2 database files to compare'); return; }
        const btn = document.getElementById('compareBtn');
        btn.disabled = true; btn.textContent = 'Comparing...';
        try {
            const resp = await fetch('/api/compare', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({databases: dbs})
            });
            const result = await resp.json();
            const div = document.getElementById('compareResult');
            div.classList.remove('hidden');
            if (result.error) {
                div.innerHTML = `<div class="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">${result.error}</div>`;
            } else {
                let html = `<div class="p-4 bg-green-50 border border-green-200 rounded-lg">
                    <p class="font-semibold text-green-800">Comparison Complete</p>
                    <p class="text-sm text-green-700 mt-1">Total messages: ${result.total_unique} | Deleted: ${result.total_deleted}</p>`;
                if (result.chats_with_deletions && Object.keys(result.chats_with_deletions).length > 0) {
                    html += `<div class="mt-3"><p class="text-sm font-medium text-green-800">Chats with deletions:</p><ul class="mt-1 text-sm text-green-700">`;
                    for (const [chat, count] of Object.entries(result.chats_with_deletions)) {
                        html += `<li>- ${chat}: ${count} deleted</li>`;
                    }
                    html += `</ul></div>`;
                }
                if (result.output_dir) {
                    html += `<p class="text-sm text-green-600 mt-2">Reports saved to: ${result.output_dir}</p>`;
                }
                html += `</div>`;
                div.innerHTML = html;
            }
        } catch(e) {
            document.getElementById('compareResult').innerHTML = `<div class="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">${e.message}</div>`;
            document.getElementById('compareResult').classList.remove('hidden');
        } finally { btn.disabled = false; btn.textContent = 'Compare & Find Deleted Messages'; }
    }

    document.getElementById('exportForm').addEventListener('submit', async function(e) {
        e.preventDefault();
        const data = getFormData();
        data.selected_chats = getSelectedChats();
        const btn = document.getElementById('exportBtn');
        btn.disabled = true;
        btn.textContent = 'Exporting...';
        btn.classList.add('opacity-50');
        document.getElementById('statusBadge').textContent = 'Running...';
        document.getElementById('statusBadge').className = 'px-3 py-1 rounded-full text-xs font-medium bg-yellow-400/20 text-yellow-200';
        showTab('output');
        clearLogs();
        appendLog('Starting export...', 'info');

        try {
            const response = await fetch('/api/export', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                const text = decoder.decode(value);
                text.split('\n').filter(Boolean).forEach(line => {
                    try {
                        const msg = JSON.parse(line);
                        appendLog(msg.message, msg.type);
                    } catch { appendLog(line, 'info'); }
                });
            }
            appendLog('Export completed!', 'info');
            document.getElementById('statusBadge').textContent = 'Done';
            document.getElementById('statusBadge').className = 'px-3 py-1 rounded-full text-xs font-medium bg-green-400/20 text-green-200';
        } catch (err) {
            appendLog('Error: ' + err.message, 'error');
            document.getElementById('statusBadge').textContent = 'Error';
            document.getElementById('statusBadge').className = 'px-3 py-1 rounded-full text-xs font-medium bg-red-400/20 text-red-200';
        } finally {
            btn.disabled = false;
            btn.textContent = 'Start Export';
            btn.classList.remove('opacity-50');
        }
    });
    </script>
</body>
</html>
'''


def create_app() -> 'Flask':
    """Create and configure the Flask application."""
    if Flask is None:
        print("Error: Flask is required for the GUI. Install it with: pip install flask")
        sys.exit(1)

    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.urandom(24).hex()

    @app.route('/')
    def index():
        return render_template_string(GUI_TEMPLATE)

    @app.route('/api/export', methods=['POST'])
    def run_export():
        from flask import Response, stream_with_context
        data = request.get_json()

        def generate():
            import subprocess
            # Build CLI args from form data
            args = ['python', '-m', 'Whatsapp_Chat_Exporter', '--no-banner']

            device = data.get('device', 'android')
            if device == 'android':
                args.append('-a')
            elif device == 'ios':
                args.append('-i')
            elif device == 'exported':
                args.append('-e')
                if data.get('exported_file'):
                    args.append(data['exported_file'])

            if data.get('db'):
                args.extend(['-d', data['db']])
            if data.get('wa'):
                args.extend(['-w', data['wa']])
            if data.get('media'):
                args.extend(['-m', data['media']])
            if data.get('backup'):
                args.extend(['-b', data['backup']])
            if data.get('key'):
                args.extend(['-k', data['key']])
            if data.get('key_image'):
                args.extend(['--key-image', data['key_image']])
            if data.get('output'):
                args.extend(['-o', data['output']])
            tz = data.get('timezone_offset', '0')
            if tz and tz != '0':
                args.extend(['--time-offset', str(tz)])

            # Output formats
            if not data.get('html', True):
                args.append('--no-html')
            if data.get('json_export'):
                args.append('-j')
            if data.get('txt'):
                args.append('--txt')
            if data.get('pdf'):
                args.append('--pdf')
            if data.get('markdown'):
                args.append('--markdown')
            if data.get('csv'):
                args.append('--csv')

            # Advanced
            if data.get('overview'):
                args.append('--overview')
            if data.get('anonymize'):
                args.append('--anonymize')
            if data.get('no_avatar'):
                args.append('--no-avatar')
            if data.get('old_theme'):
                args.append('--old-theme')
            if data.get('move_media'):
                args.append('-c')
            if data.get('separate_media'):
                args.append('--create-separated-media')
            if data.get('business'):
                args.append('--business')
            if data.get('fix_dot_files'):
                args.append('--fix-dot-files')

            # Filters
            chat_names = data.get('chat_name', '')
            if chat_names:
                for name in chat_names.split(','):
                    name = name.strip()
                    if name:
                        args.extend(['--chat-name', name])
            date_filter = data.get('date_filter', '')
            if date_filter:
                args.extend(['--date', date_filter])

            # Selected chats filter
            selected_chats = data.get('selected_chats', [])
            if selected_chats:
                for jid in selected_chats:
                    phone = jid.split('@')[0] if '@' in jid else jid
                    if phone:
                        args.extend(['--include', phone])

            yield json.dumps({"type": "info", "message": f"Running: {' '.join(args)}"}) + "\n"

            try:
                process = subprocess.Popen(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                for line in process.stdout:
                    line = line.strip()
                    if line:
                        msg_type = "error" if "[ERROR]" in line else "warning" if "[WARNING]" in line else "info"
                        yield json.dumps({"type": msg_type, "message": line}) + "\n"

                process.wait()
                if process.returncode == 0:
                    yield json.dumps({"type": "info", "message": "Export completed successfully!"}) + "\n"
                else:
                    yield json.dumps({"type": "error", "message": f"Export failed with code {process.returncode}"}) + "\n"
            except Exception as e:
                yield json.dumps({"type": "error", "message": str(e)}) + "\n"

        return Response(stream_with_context(generate()), mimetype='text/plain')

    @app.route('/api/list-chats', methods=['POST'])
    def list_chats():
        """Scan database and list available chats for selection."""
        import sqlite3
        data = request.get_json()
        device = data.get('device', 'android')

        # Determine DB path
        db_path = data.get('db', '')

        # Handle encrypted backup: decrypt first if needed
        backup = data.get('backup', '')
        key_input = data.get('key', '')
        if backup and key_input and device == 'android':
            # Try to decrypt first
            import subprocess
            decrypt_args = ['python', '-m', 'Whatsapp_Chat_Exporter', '-a',
                          '--no-html', '--no-banner', '-b', backup, '-k', key_input]
            if db_path:
                decrypt_args.extend(['-d', db_path])
            else:
                db_path = 'msgstore.db'
                decrypt_args.extend(['-d', db_path])
            # Run a quick decrypt-only pass
            try:
                subprocess.run(decrypt_args + ['-j', '/dev/null'],
                             capture_output=True, text=True, timeout=120)
            except Exception:
                pass

        if not db_path:
            db_path = 'msgstore.db' if device == 'android' else '7c7fba66680ef796b916b067077cc246adacf01d'

        if not os.path.isfile(db_path):
            return jsonify({"error": f"Database not found: {db_path}. "
                          "Make sure the file exists or decrypt the backup first."})

        chats = []
        try:
            with sqlite3.connect(db_path) as db:
                db.row_factory = sqlite3.Row
                c = db.cursor()

                if device == 'android':
                    # Try new schema first
                    try:
                        c.execute("""
                            SELECT COALESCE(jid.raw_string, '') as jid,
                                   chat.subject as name,
                                   COUNT(message._id) as msg_count
                            FROM chat
                                INNER JOIN jid ON jid._id = chat.jid_row_id
                                LEFT JOIN message ON message.chat_row_id = chat._id
                            GROUP BY chat._id
                            HAVING msg_count > 0
                            ORDER BY MAX(message.timestamp) DESC
                        """)
                    except sqlite3.OperationalError:
                        # Legacy schema
                        c.execute("""
                            SELECT DISTINCT key_remote_jid as jid,
                                   NULL as name,
                                   COUNT(*) as msg_count
                            FROM messages
                            WHERE key_remote_jid != '-1'
                            GROUP BY key_remote_jid
                            HAVING msg_count > 0
                            ORDER BY MAX(timestamp) DESC
                        """)

                    for row in c.fetchall():
                        jid = row['jid'] or ''
                        name = row['name']
                        if not name and '@' in jid:
                            name = jid.split('@')[0]
                        chats.append({
                            "jid": jid,
                            "name": name or jid,
                            "message_count": row['msg_count']
                        })
                else:
                    # iOS
                    c.execute("""
                        SELECT ZCONTACTJID as jid,
                               ZPARTNERNAME as name,
                               COUNT(ZWAMESSAGE.Z_PK) as msg_count
                        FROM ZWACHATSESSION
                            LEFT JOIN ZWAMESSAGE ON ZWAMESSAGE.ZCHATSESSION = ZWACHATSESSION.Z_PK
                        GROUP BY ZCONTACTJID
                        HAVING msg_count > 0
                        ORDER BY MAX(ZWAMESSAGE.ZMESSAGEDATE) DESC
                    """)
                    for row in c.fetchall():
                        chats.append({
                            "jid": row['jid'] or '',
                            "name": row['name'] or (row['jid'] or '').split('@')[0],
                            "message_count": row['msg_count']
                        })

        except Exception as e:
            return jsonify({"error": str(e)})

        return jsonify({"chats": chats})

    @app.route('/api/connected/validate-key', methods=['POST'])
    def connected_validate_key():
        """Validate and clean a key from various input sources."""
        data = request.get_json()

        try:
            key = None

            if data.get('key_hex'):
                from Whatsapp_Chat_Exporter.key_extractor import clean_key_input
                key = clean_key_input(data['key_hex'])
                if not key:
                    return jsonify({"error": "Invalid key. Expected 64 hex characters (0-9, a-f). "
                                  "You can include spaces, dashes, or colons as separators."})

            elif data.get('key_file'):
                from Whatsapp_Chat_Exporter.wa_connected import read_key_file
                key = read_key_file(data['key_file'])
                if not key:
                    return jsonify({"error": f"Could not read key from file: {data['key_file']}"})

            elif data.get('key_image'):
                from Whatsapp_Chat_Exporter.key_extractor import extract_key_from_image
                key = extract_key_from_image(data['key_image'])
                if not key:
                    return jsonify({"error": "Could not extract key from image. "
                                  "Make sure pytesseract is installed: pip install pytesseract Pillow"})

            if key:
                return jsonify({"key": key})
            return jsonify({"error": "No key input provided"})

        except Exception as e:
            return jsonify({"error": str(e)})

    @app.route('/api/connected/adb-status', methods=['POST'])
    def connected_adb_status():
        """Check ADB devices and WhatsApp status on each."""
        try:
            from Whatsapp_Chat_Exporter.wa_connected import check_adb_status, check_whatsapp_on_device
            status = check_adb_status()
            if status["available"] and status["devices"]:
                for dev in status["devices"]:
                    wa_info = check_whatsapp_on_device(dev["serial"])
                    dev["whatsapp_installed"] = wa_info.get("installed", False)
                    dev["whatsapp_version"] = wa_info.get("version")
                    dev["has_key"] = wa_info.get("has_key", False)
                    dev["is_root"] = wa_info.get("is_root", False)
            return jsonify(status)
        except Exception as e:
            return jsonify({"available": False, "devices": [], "error": str(e)})

    @app.route('/api/connected/adb-extract', methods=['POST'])
    def connected_adb_extract():
        """Extract key from connected Android device/emulator via ADB."""
        try:
            from Whatsapp_Chat_Exporter.wa_connected import extract_key_adb_auto
            key = extract_key_adb_auto()
            if key:
                return jsonify({"key": key})
            return jsonify({"error": "Could not extract key. "
                          "Make sure WhatsApp is installed and set up in the emulator, "
                          "and that the emulator has root access (most emulators do by default)."})
        except Exception as e:
            return jsonify({"error": str(e)})

    @app.route('/api/compare', methods=['POST'])
    def compare_dbs():
        """Compare multiple databases for deleted messages."""
        data = request.get_json()
        db_paths = data.get('databases', [])

        if len(db_paths) < 2:
            return jsonify({"error": "At least 2 databases are required"})

        for path in db_paths:
            if not os.path.isfile(path):
                return jsonify({"error": f"File not found: {path}"})

        try:
            from Whatsapp_Chat_Exporter.db_comparator import compare_databases_interactive
            output_dir = "comparison_result"
            report = compare_databases_interactive(db_paths, output_dir)
            return jsonify({
                "total_unique": report.total_unique_messages,
                "total_deleted": report.total_deleted_messages,
                "total_chats": report.total_chats,
                "chats_with_deletions": report.chats_with_deletions,
                "output_dir": output_dir,
            })
        except Exception as e:
            return jsonify({"error": str(e)})

    return app


def main(host: str = "127.0.0.1", port: int = 5000, open_browser: bool = True):
    """Launch the GUI server."""
    if Flask is None:
        print("Error: Flask is required for the GUI.")
        print("Install it with: pip install flask")
        sys.exit(1)

    app = create_app()
    url = f"http://{host}:{port}"

    print(f"\n  WhatsApp Chat Exporter - Web GUI")
    print(f"  ================================")
    print(f"  Running at: {url}")
    print(f"  Press Ctrl+C to stop\n")

    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
