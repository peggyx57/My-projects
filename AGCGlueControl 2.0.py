import dis
from logging import root
from tkinter import filedialog
from turtle import mode, st
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.pyplot import tick_params
import seaborn as sns
import pandas as pd
import datetime
import json
import random
import csv
import os
import sys
import shutil # Potřeba pro archivaci souborů
from PIL import Image
import numpy as np
from Vocabulary_SPC import TEXTS
import serial
import re
from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk


heslo_kamkoliv = "admin"  # Heslo pro přístup do nastavení a editaci modelů
pocet_pro_ucl_lcl_fix_v_pripade_vypocitanych_control_limitu= 15 # počet, kdy se z not fixed stane fixed u UCL/LCL
minimalni_pocet_namerench_bodu_spc=10 # prostě když nemám pevné limity, tak kolik hodnot je potřeba por výpočet UCL/LCL
pocet_minut_na_rozjezd=10
port_PC_pro_kabel_vahy = "COM2" # <-- ZMĚŇ PODLE SVÉHO PC (např. COM4, COM5)

# --- DATA A TEXTY ---
OPERATORS_JSON = """
[
    {"id": 0, "name": "Default"}
]
"""

class PredictionDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        t = TEXTS[parent.jazyk]
        super().__init__(parent)
        self.parent = parent
        
        
        # Nastavení okna
        self.title(t["prediction"])
        self.parent.umistit_okno_na_obrazovce(self, 900, 600)
        self.grab_set()
        
        # 1. HLAVNÍ KONTEJNERY
        # Horní panel pro Textové info
        self.info_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.info_frame.pack(fill="x", padx=20, pady=(20, 10))
        
        self.lbl_info = ctk.CTkLabel(self.info_frame, text="Výpočet...", font=("Arial", 16, "bold"), justify="left")
        self.lbl_info.pack(side="left")

        # Dolní panel pro Graf
        self.graph_frame = ctk.CTkFrame(self)
        self.graph_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # 2. VÝPOČET A VYKRESLENÍ
        self._analyzovat_a_vykreslit()

    def _analyzovat_a_vykreslit(self):
        # 1. ZÍSKÁNÍ DAT
        # Zavoláme tu funkci nahoře. Ona vrátí slovník 'vysledek'.
        t= TEXTS[self.parent.jazyk]
        data = self.parent.vypocitat_trend_a_status()
        
        # 2. POUŽITÍ DAT PRO TEXTY
        # Vytáhneme si text a barvu ze slovníku
        text_zpravy = data["text"]
        barva_zpravy = data["barva"]
        
        self.lbl_info.configure(text=text_zpravy, text_color=barva_zpravy)

        # 3. POUŽITÍ DAT PRO GRAF
        if data["dostatek_dat"]:
            # Vytáhneme si čísla pro graf
            # Všimni si: data["x"], data["y"]... to jsou klíče z toho slovníku
            self._kreslit_graf(
                x_hist=data["x"], 
                y_hist=data["y"], 
                slope=data["slope"], 
                intercept=data["intercept"]
            )
        else:
            self.lbl_info.configure(text=t["not_enough_data_pred"].format(minimum=self.parent.minimalni_pocet_namerench_bodu_spc))

    def _kreslit_graf(self, x_hist, y_hist, slope, intercept):
        t= TEXTS[self.parent.jazyk]
        bg_color, face_color, text_color = self.parent.get_graph_colors()

        fig = Figure(figsize=(8, 4), dpi=100)
        fig.patch.set_facecolor(bg_color)
        ax = fig.add_subplot(111)
        ax.set_facecolor(face_color)
        ax.tick_params(colors=text_color)
        ax.grid(True, color=text_color, alpha=0.15)

        # 1. Historická data (modré tečky)
        ax.plot(x_hist, y_hist, 'o', color='#3B8ED0', alpha=0.6, label=t["history"])
        
        # 2. Trendová přímka (minulost + budoucnost)
        # Budoucnost: Přidáme třeba 50 bodů dopředu
        future_steps = 50
        x_future = np.arange(len(x_hist) + future_steps)
        y_trend = slope * x_future + intercept
        
        # Vykreslíme trend
        # Část přes historii (plná čára)
        ax.plot(x_hist, y_trend[:len(x_hist)], color='purple', linewidth=2, alpha=0.8, label=t["trend_fit"])
        # Část do budoucnosti (čárkovaná)
        ax.plot(x_future[len(x_hist):], y_trend[len(x_hist):], color='purple', linestyle='--', linewidth=2, label=t["prediction"])

        # 3. Limity (USL, LSL, Target)
        ax.axhline(self.parent.usl, color='#FF1744', linestyle='--', alpha=0.5, label="USL/LSL")
        ax.axhline(self.parent.lsl, color='#FF1744', linestyle='--', alpha=0.5, label="")
        ax.axhline(self.parent.target, color='#00E676', linestyle='-', alpha=0.3, label=t["target"])
        
        if hasattr(self.parent, 'fixed_ucl') and self.parent.fixed_ucl is not None:
             ax.axhline(self.parent.fixed_ucl, color='orange', linestyle='-', alpha=0.5, label="UCL/LCL")
             
        if hasattr(self.parent, 'fixed_lcl') and self.parent.fixed_lcl is not None:
             ax.axhline(self.parent.fixed_lcl, color='orange', linestyle='-', alpha=0.5, label="")
        # Popisky
        ax.set_title(t["trend_analysis"], color=text_color)
        ax.set_ylabel(t["value"], color=text_color)
        ax.set_xlabel(t["measurements_count"], color=text_color)
        
        ax.tick_params(colors=text_color)
        for spine in ax.spines.values(): spine.set_edgecolor(text_color)
        
        ax.legend(facecolor=bg_color, labelcolor=text_color, loc='upper right', fontsize='small')

        # Vložení do okna
        canvas = FigureCanvasTkAgg(fig, master=self.graph_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

class DataAnalysisDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        t = TEXTS[parent.jazyk]
        super().__init__(parent)
        self.parent = parent
        self.df = parent.df.copy() # Pracujeme s kopií dat
        self.grab_set()
        
        # Nastavení okna
        self.title(f"{t['data_analysis']}: {parent.aktualni_model}")
        
        self.parent.umistit_okno_na_obrazovce(self, 1100, 650) # Trochu širší
        
        # Grid layout
        self.grid_columnconfigure(0, weight=0, minsize=280) # Levý panel širší kvůli Cpk
        self.grid_columnconfigure(1, weight=1)              # Pravý panel (obsah)
        self.grid_rowconfigure(0, weight=1)

        # --- 1. LEVÝ PANEL (Statistiky a Ovládání) ---
        self.left_frame = ctk.CTkFrame(self, corner_radius=0)
        self.left_frame.grid(row=0, column=0, sticky="nsew")
        
        # Nadpis
        ctk.CTkLabel(self.left_frame, text=t["view"], font=("Arial", 18, "bold")).pack(pady=(20, 10))

        # Přepínač
        self.view_selector = ctk.CTkSegmentedButton(
            self.left_frame, 
            values=[t["histogram"], t["data_table"]],
            command=self.prepni_zobrazeni
        )
        self.view_selector.set(t["histogram"])
        self.view_selector.pack(pady=10, padx=20)

        # Oddělovač
        ctk.CTkFrame(self.left_frame, height=2, fg_color="gray50").pack(fill="x", padx=20, pady=20)

        # Statistiky
        ctk.CTkLabel(self.left_frame, text="Statistiky & Cpk", font=("Arial", 16, "bold")).pack(pady=(0, 10))
        
        self.stats_frame = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        self.stats_frame.pack(fill="x", padx=20)

        self._vypocitat_a_zobrazit_statistiky()

        # --- 2. PRAVÝ PANEL (Obsah) ---
        self.right_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.right_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.right_frame.grid_rowconfigure(0, weight=1)
        self.right_frame.grid_columnconfigure(0, weight=1)

        # Inicializace obsahu
        self.current_content = None
        self.prepni_zobrazeni(t["histogram"])

    def _vypocitat_a_zobrazit_statistiky(self):
        """Vypočítá mean, std, limity A HLAVNĚ Cp/Cpk."""
        t= TEXTS[self.parent.jazyk]
        if self.df.empty:
            return
        for widget in self.stats_frame.winfo_children():
            widget.destroy()
        values = self.df["Hodnota"]
        mean = values.mean()
        std_dev = values.std()
        count = len(values)
        
        usl = self.parent.usl
        lsl = self.parent.lsl

        # --- VÝPOČET Cp a Cpk ---
        cp = 0
        cpk = 0
        if std_dev > 0:
            # Cp = (USL - LSL) / (6 * sigma)
            cp = (usl - lsl) / (6 * std_dev)
            
            # Cpk = min( (USL - Mean)/(3*sigma) , (Mean - LSL)/(3*sigma) )
            cpu = (usl - mean) / (3 * std_dev)
            cpl = (mean - lsl) / (3 * std_dev)
            cpk = min(cpu, cpl)

        # Zjištění stavu UCL/LCL
        ucl_info = " (Auto)"
        lcl_info = " (Auto)"
        val_ucl = None
        val_lcl = None

        if hasattr(self.parent, 'fixed_ucl') and self.parent.fixed_ucl is not None:
            val_ucl = self.parent.fixed_ucl
            val_lcl = self.parent.fixed_lcl
            ucl_info = " (Fix)"
            lcl_info = " (Fix)"
        elif std_dev > 0 and count >= 2:
            val_ucl = mean + (3 * std_dev)
            val_lcl = mean - (3 * std_dev)
        
        # Seznam statistik k zobrazení
        stats = [
            (f"{t['stat_count']}:", f"{count}"),
            ("---", "---"),
            (f"{t['usl']}:", f"{usl}"),
            (f"{t['target']}:", f"{self.parent.target}"),
            (f"{t['lsl']}:", f"{lsl}"),
            ("---", "---"),
            (f"{t['stat_mean']}:", f"{mean:.3f}"),
            (f"{t['stat_sigma']}:", f"{std_dev:.3f}"),
            ("---", "---"),
            (f"{t['stat_cp']}:", f"{cp:.2f}"), 
            (f"{t['stat_cpk']}:", f"{cpk:.2f}"),
            ("---", "---"),
            (f"UCL{ucl_info}:", f"{val_ucl:.3f}" if val_ucl else "N/A"),
            (f"LCL{lcl_info}:", f"{val_lcl:.3f}" if val_lcl else "N/A")
            ]

        for label, value in stats:
            row = ctk.CTkFrame(self.stats_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            
            lbl_key = ctk.CTkLabel(row, text=label, anchor="w", font=("Arial", 12))
            lbl_key.pack(side="left")
            
            # Barvičky
            color = "gray" if "---" in value or "N/A" in value else self.parent.lbl_model_display.cget("text_color")
            font_weight = "normal"
            
            # Zvýraznění Cpk (Zelená = dobré, Červená = špatné)
            if "Cpk" in label:
                font_weight = "bold"
                try:
                    val_float = float(value)
                    if val_float >= 1.33: color = "#00E676" # Super zelená
                    elif val_float >= 1.0: color = "orange" # Ujde to
                    else: color = "#FF1744" # Průšvih
                except: pass
            
            # Zvýraznění Mean a Cp
            if t["stat_mean"] in label or t["stat_cp"] in label: # Mezera u Cp aby to nechytlo Cpk
                font_weight = "bold"

            lbl_val = ctk.CTkLabel(row, text=value, anchor="e", font=("Arial", 12, font_weight), text_color=color)
            lbl_val.pack(side="right")

    def prepni_zobrazeni(self, volba):
        # Načteme aktuální texty, abychom mohli porovnat, co přišlo z tlačítka
        t = TEXTS[self.parent.jazyk]

        for widget in self.right_frame.winfo_children():
            widget.destroy()

        # Porovnáváme s PŘELOŽENÝM textem, ne s "Histogram" nebo "Tabulka dat"
        if volba == t["histogram"]:
            self._vykreslit_histogram()
        elif volba == t["data_table"]:  # Tady byl ten problém!
            self._vykreslit_tabulku()

    def _vykreslit_histogram(self):
        t = TEXTS[self.parent.jazyk]
        
        # 1. Vyčistíme rámec (aby se grafy nepřekrývaly při obnovení)
        for widget in self.right_frame.winfo_children():
            widget.destroy()

        if self.df.empty:
            ctk.CTkLabel(self.right_frame, text=t.get("no_data_for_histogram", "Žádná data")).pack(expand=True)
            return

        # 2. Nastavení barev a stylu
        bg_color, face_color, text_color = self.parent.get_graph_colors()
        
        # Vytvoření Figure
        fig = Figure(figsize=(6, 5), dpi=100)
        fig.patch.set_facecolor(bg_color)
        ax = fig.add_subplot(111)
        ax.set_facecolor(face_color) # Pozadí uvnitř grafu
        
        # Příprava dat
        vals = self.df["Hodnota"]
        mean = vals.mean()
        std = vals.std()

        # 3. HISTOGRAM (Sloupce)
        # density=False -> Osa Y ukazuje POČET KUSŮ (Counts)
        counts, bins, patches = ax.hist(
            vals, 
            bins='auto',      # Automatický počet sloupců
            density=False,    # <--- DŮLEŽITÉ: Chceme počty, ne hustotu
            color='#3B8ED0', 
            alpha=0.7, 
            rwidth=0.9,       # Mezery mezi sloupci
            edgecolor=text_color, 
            label=t.get("data", "Naměřeno")
        )
        
        # 4. GAUSSOVA KŘIVKA (Přizpůsobená)
        if std > 0:
            # Rozsah osy X
            xmin, xmax = ax.get_xlim()
            # Roztáhneme osu X, aby se tam vešly i limity
            limit_min = min(xmin, self.parent.lsl - 0.2)
            limit_max = max(xmax, self.parent.usl + 0.2)
            ax.set_xlim(limit_min, limit_max)
            
            x = np.linspace(limit_min, limit_max, 100)
            
            # a) Výpočet matematické hustoty (Normal PDF)
            # Používám čistý numpy vzorec, abys nemusel importovat scipy
            p = (1 / (np.sqrt(2 * np.pi) * std)) * np.exp(-0.5 * ((x - mean) / std)**2)
            
            # b) ŠKÁLOVÁNÍ (To je to kouzlo)
            # Aby byla křivka vidět, musíme ji vynásobit počtem dat a šířkou sloupce
            bin_width = bins[1] - bins[0] # Šířka jednoho sloupce
            pocet_dat = len(vals)
            
            p_scaled = p * pocet_dat * bin_width
            
            ax.plot(x, p_scaled, color='#FF9800', linewidth=2.5, label="Gauss")

        # 5. LIMITY (Svislé čáry)
        ax.axvline(self.parent.usl, color='#FF1744', linestyle='--', linewidth=2, label='USL/LSL')
        ax.axvline(self.parent.lsl, color='#FF1744', linestyle='--', linewidth=2)
        ax.axvline(self.parent.target, color='#00E676', linestyle='-', linewidth=2, label='Target')
        ax.axvline(mean, color=text_color, linestyle=':', linewidth=2, alpha=0.6, label='Průměr')

        # 6. POPISKY
        ax.set_title(t["histogram"], color=text_color, fontsize=14, fontweight='bold')
        ax.set_xlabel(t["value"] + " (g)", color=text_color)
        ax.set_ylabel(t["count"], color=text_color) # Správný popisek!
        
        # Barvy os a mřížky
        ax.tick_params(colors=text_color)
        ax.grid(True, color=text_color, alpha=0.1) # Jemná mřížka
        for spine in ax.spines.values(): spine.set_edgecolor(text_color)
        
        # Legenda
        ax.legend(facecolor=bg_color, labelcolor=text_color, loc='upper right', fontsize='small')

        # 7. Vykreslení do Tkinter
        canvas = FigureCanvasTkAgg(fig, master=self.right_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    def _vykreslit_tabulku(self):
        t = TEXTS[self.parent.jazyk]
        # ... (Tato funkce zůstává stejná jako ve tvém kódu) ...
        # Jen ji sem zkopíruj z toho co jsi poslal
        mode = ctk.get_appearance_mode()
        if mode == "Dark":
            bg = "#2b2b2b"      # Tmavě šedá pro pozadí tabulky
            text_color = "white"      # Bílá pro text
            header_bg = "#1a1a1a"     # Ještě tmavší pro hlavičku
            selected_bg = "#1f538d"   # Modrá pro vybraný řádek (ctk modrá)
        else:
            bg = "white"
            text_color = "black"
            header_bg = "#e1e1e1"     # Světle šedá pro hlavičku
            selected_bg = "#3a7ebf"

        style = ttk.Style()
       # bg = "#333333" if ctk.get_appearance_mode() == "Dark" else "white"
        #fg = "white" if ctk.get_appearance_mode() == "Dark" else "black"
        style.theme_use("clam")
        style.configure("Treeview", 
                        background=bg, 
                        foreground=text_color, 
                        fieldbackground=bg,
                        borderwidth=0,
                        font=("Arial", 11),
                        rowheight=25)
        style.configure("Treeview.Heading", font=("Arial", 12, "bold"), background=header_bg, foreground=text_color, relief="flat")
        style.map("Treeview.Heading",
                  background=[('active', selected_bg)])
        style.map("Treeview",
                  background=[('selected', selected_bg)],
                  foreground=[('selected', 'white')])
        
        cols = ("Datum", "Cas", "Hodnota", "Operator", "Smena", "Status")
        tree = ttk.Treeview(self.right_frame, columns=cols, show="headings", style="Treeview")
        
        tree.heading("Datum", text=t["date"])
        tree.heading("Cas", text=t["time"])
        tree.heading("Hodnota", text=t["value"])
        tree.heading("Operator", text=t["operator"])
        tree.heading("Smena", text=t["shift"])
        tree.heading("Status", text=t["status"])
        
        tree.column("Datum", width=100, anchor="center")
        tree.column("Cas", width=80, anchor="center")
        tree.column("Hodnota", width=80, anchor="center")
        tree.column("Operator", width=150, anchor="center")
        tree.column("Smena", width=80, anchor="center")
        tree.column("Status", width=60, anchor="center")

        #scrollbar = ttk.Scrollbar(self.right_frame, orient="vertical", command=tree.yview)
        #tree.configure(yscrollcommand=scrollbar.set)
        
        #scrollbar.pack(side="right", fill="y")
        scrollbar = ctk.CTkScrollbar(
            self.right_frame, 
            orientation="vertical", 
            command=tree.yview,
            width=16,               # Trochu širší, aby se dobře chytal
            fg_color="transparent", # Pozadí "koryt" (transparentní splyne s rámem)
            corner_radius=8         # Kulaté rohy
        )
        
        # Propojení s tabulkou
        tree.configure(yscrollcommand=scrollbar.set)
        
        # Zobrazení
        scrollbar.pack(side="right", fill="y", padx=(0, 5), pady=5)
        tree.pack(side="left", fill="both", expand=True)

        for index, row in self.df.iloc[::-1].iterrows():
            tag = "ok" if row["Status"] == "OK" else "nok"
            
            # Bezpečné získání datumu (kdyby chyběl)
            r_datum = str(row.get("Datum", "?"))
            if r_datum == "nan": r_datum = "?"
            elif "-" in r_datum:
                # Rozdělíme 2026-02-18 podle pomlček a složíme jako 18.02.2026
                p = r_datum.split("-")
                if len(p) == 3:
                    r_datum = f"{p[2]}.{p[1]}.{p[0]}"
            vals = (r_datum, row["Cas"], row["Hodnota"], row["Operator"], row["Smena"], row["Status"])
            tree.insert("", "end", values=vals, tags=(tag,))

        tree.tag_configure("nok", foreground="#FF1744")

        self.menu_tabulka = tk.Menu(self, tearoff=0)
        self.menu_tabulka.add_command(label=t["delete_record"], command=self.smazat_vybrany_radek)
        
        # Bind pravého tlačítka na Treeview
        tree.bind("<Button-3>", self.zobrazit_menu_tabulky)
        self.tree = tree

    def zobrazit_menu_tabulky(self, event):
        try:
            self.menu_tabulka.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu_tabulka.grab_release()

    def smazat_vybrany_radek(self):
        t = TEXTS[self.parent.jazyk]
        
        # 1. Zjistit, co je vybráno (vrátí seznam ID všech vybraných řádků)
        selected_items = self.tree.selection()
        if not selected_items: return
        
        pocet = len(selected_items)
        
        # 2. Zeptat se na potvrzení (mírně upravená zpráva pro množné číslo)
        msg_vice_zaznamu= t["confirm_delete_multiple"].format(count=pocet)
        msg = t["confirm_delete"] if pocet == 1 else msg_vice_zaznamu
        if not messagebox.askyesno(t["delete"], msg, parent=self):
            return

        # --- KONTROLA HESLA ---
        if not self.parent.overit_heslo(okno=self):
            return

        # 3. PŘÍPRAVA DAT K SMAZÁNÍ
        # Vytvoříme si seznam dvojic (datum, cas), které chceme smazat
        to_delete = []
        for item in selected_items:
            vals = self.tree.item(item)['values']

            datum_z_tabulky = str(vals[0])
            cas_z_tabulky = str(vals[1])

            # --- PŘEVOD ZPĚT NA FORMÁT CSV (RRRR-MM-DD) ---
            if "." in datum_z_tabulky:
                p = datum_z_tabulky.split(".")
                if len(p) == 3:
                    # Předpokládáme, že v tabulce je DD.MM.RRRR a v CSV RRRR-MM-DD
                    # Musíme zachovat případné nuly, takže p[2] je rok, p[1] měsíc, p[0] den
                    datum_pro_csv = f"{p[2]}-{p[1]}-{p[0]}"
                else:
                    datum_pro_csv = datum_z_tabulky
            else:
                datum_pro_csv = datum_z_tabulky
            # Uložíme jako tuple (str(Datum), str(Cas))
            to_delete.append((datum_pro_csv, cas_z_tabulky))

        aktualni_model = self.parent.aktualni_model
        aktualni_linka = self.parent.current_set_line

        try:
            # 4. NAČÍST CELÝ SOUBOR
            full_df = pd.read_csv(self.parent.cesta_data, sep=';', decimal=',', on_bad_lines='skip')
            full_df["Datum"] = full_df["Datum"].astype(str)
            full_df["Cas"] = full_df["Cas"].astype(str)
            
            # 5. VYTVOŘENÍ MASKY PRO SMAZÁNÍ (PRO VŠECHNY POLOŽKY)
            # Začneme s maskou, která je všude False
            maska_ke_smazani_celkova = pd.Series([False] * len(full_df))

            for d, c in to_delete:
                # Pro každou položku vytvoříme dílčí masku
                maska_dilci = (
                    (full_df['Datum'] == d) & 
                    (full_df['Cas'] == c) &
                    (full_df['Model'] == aktualni_model) &
                    (full_df['Linka'] == aktualni_linka)
                )
                # Sloučíme s celkovou maskou pomocí OR (|)
                maska_ke_smazani_celkova = maska_ke_smazani_celkova | maska_dilci
            
            pocet_nalezenych = maska_ke_smazani_celkova.sum()
            print(f"Počet záznamů k smazání: {pocet_nalezenych}")
            if pocet_nalezenych == 0:
                messagebox.showwarning(t["error"], t["record_not_found"], parent=self)
                return

            # 6. SMAZAT A ULOŽIT ZPĚT
            full_df = full_df[~maska_ke_smazani_celkova]
            full_df.to_csv(self.parent.cesta_data, sep=";", index=False, decimal=",")
            print(f"Smazáno {pocet_nalezenych} záznamů z CSV.")

        except Exception as e:
            messagebox.showerror(t["error"], f"{t['error_writing_file']}:\n{e}", parent=self)
            return

        # 7. AKTUALIZACE PAMĚTI APLIKACE (Local & Parent)
        # Musíme to provést i pro data v paměti
        
        # Funkce pro aplikaci mazání na DataFrame v paměti
       # 7. AKTUALIZACE PAMĚTI APLIKACE (Local & Parent)
        
        def apply_deletion_to_memory(df_target):
            if df_target.empty:
                return df_target
            
            # OPRAVA: Vytvoříme masku, která má STEJNÝ INDEX jako cílová tabulka
            maska_mem = pd.Series([False] * len(df_target), index=df_target.index)
            
            # Pro jistotu převedeme sloupce na string
            df_target["Datum"] = df_target["Datum"].astype(str)
            df_target["Cas"] = df_target["Cas"].astype(str)
            
            for d, c in to_delete:
                # Tady se teď Pandas trefí přesně, protože indexy sedí
                m = (df_target['Datum'] == d) & (df_target['Cas'] == c)
                maska_mem = maska_mem | m
            
            # Vrátíme profiltrovanou tabulku
            return df_target[~maska_mem].copy()

        # Aplikujeme na obě tabulky v paměti
        self.df = apply_deletion_to_memory(self.df)
        self.parent.df = apply_deletion_to_memory(self.parent.df)

        # 8. REFRESH ZOBRAZENÍ
        if self.df.empty:
            print("Žádná data pro tento model nezbyla, zavírám okno.")
            # Nejdříve aktualizujeme hlavní okno na pozadí
            self.parent.aktualizovat_semafor()
            self.parent.update_graph()
            # Poté zavřeme okno historie
            self.destroy()
        else:
            # Pokud data zbyla, normálně refreshneme tabulku a statistiky
            self.prepni_zobrazeni(t["data_table"])
            self._vypocitat_a_zobrazit_statistiky()
            self.parent.aktualizovat_semafor()
            self.parent.update_graph()

class ModernMenu(ctk.CTkToplevel):
    def __init__(self, parent, x, y, options):
        super().__init__(parent)
        
        # 1. Zjištění režimu (Dark/Light) a Tématu
        appearance_mode = ctk.get_appearance_mode() # "Light" nebo "Dark"
        is_dark = appearance_mode == "Dark"
        
        # Definice barev podle režimu
        bg_color = "#2b2b2b" if is_dark else "#ffffff"
        text_color_default = "white" if is_dark else "black"
        hover_color_default = "#3a3a3a" if is_dark else "#ebebeb"
        separator_color = "gray40" if is_dark else "gray80"
        
        # Barva rámečku podle tématu aplikace (např. blue, green)
        # Získáme hex kód aktuálního tématu
        border_color = ctk.ThemeManager.theme["CTkButton"]["fg_color"][1 if is_dark else 0]

        # 2. Nastavení okna
        self.overrideredirect(True) 
        self.attributes("-topmost", True)

        transparent_color_key = "#000001" # Skoro černá, ale ne úplně
        self.configure(fg_color=transparent_color_key)
        
        if sys.platform.startswith("win"):
            self.attributes("-transparentcolor", transparent_color_key)

        # Hlavní kontejner s rámečkem
        # Přidali jsme pady=2 uvnitř frame.pack, aby tlačítka nebyla nalepená na horní/dolní okraj rámečku
        self.frame = ctk.CTkFrame(self, fg_color=bg_color, border_width=2, border_color=border_color, corner_radius=10)
        self.frame.pack(fill="both", expand=True)

        # 3. Vykreslení položek
        # Přidáme trochu místa nahoře v menu
        #ctk.CTkFrame(self.frame, height=5, fg_color="transparent").pack()

        for item in options:
            text = item.get("text")
            command = item.get("command")
            is_separator = item.get("separator", False)
            
            # Pokud položka nemá vlastní barvu (např. červená pro smazání), použije se default podle módu
            item_text_color = item.get("text_color", text_color_default)
            item_hover_color = item.get("hover_color", hover_color_default)

            if is_separator:
                # Čára (Separator)
                line = ctk.CTkFrame(self.frame, height=2, fg_color=separator_color, corner_radius=10)
                # pady=5 zajistí odstup čáry od tlačítek
                line.pack(fill="x", padx=15, pady=0)
            else:
                # Tlačítko (položka menu)
                btn = ctk.CTkButton(
                    self.frame, 
                    text=text, 
                    command=lambda cmd=command: self._on_click(cmd),
                    fg_color="transparent", 
                    text_color=item_text_color,
                    hover_color=item_hover_color,
                    anchor="center", # ZMĚNA: Zarovnání na střed
                    height=32,       # Trochu menší výška pro eleganci
                    corner_radius=6,
                    font=("Arial", 14) # O něco větší písmo
                )
                # padx=10 (odstup z boků), pady=3 (odstup mezi tlačítky)
                btn.pack(fill="x", padx=10, pady=8)

        # Přidáme trochu místa dole v menu
        #ctk.CTkFrame(self.frame, height=5, fg_color="transparent").pack()

        # 4. Pozicování a velikost
        self.update_idletasks()
        width = 200 # Trochu širší menu, aby se text vešel hezky na střed
        height = self.frame.winfo_reqheight()
        
        # Korekce pozice (aby menu neúteklo z obrazovky)
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        
        if x + width > screen_w: x -= width
        if y + height > screen_h: y -= height
            
        self.geometry(f"{width}x{height}+{x}+{y}")
        
        # 5. Zavření při ztrátě fokusu
        self.bind("<FocusOut>", lambda e: self.destroy())
        self.focus_force()

    def _on_click(self, command):
        self.destroy()
        if command:
            command()

class PasswordDialog(ctk.CTkToplevel):
    def __init__(self, parent, jazyk="CZ"):
        super().__init__(parent)
        self.t = TEXTS.get(jazyk, TEXTS["CZ"])
        # Proměnná pro uložení výsledku
        self.password = None
        
        # 1. Základní nastavení okna
        self.title(self.t["password_dialog_title"])
        self.resizable(False, False)
        
        # Skryjeme okno, dokud nebude hotové
        self.withdraw()
        
        # DŮLEŽITÉ: Řekneme systému, že toto okno patří rodiči
        # To pomáhá, aby dialog nezmizel pod oknem nastavení
        self.transient(parent) 
        self.attributes("-topmost", True)
        
        # UI Prvky
        self.label = ctk.CTkLabel(self, text=self.t["enter_password"], font=("Arial", 14, "bold"))
        self.label.pack(pady=(25, 10))
        
        self.entry = ctk.CTkEntry(self, width=200, show="*", font=("Arial", 14))
        self.entry.pack(pady=5)
        
        # Focus kurzoru se zpožděním (aby opravdu naskočil)
        self.after(100, lambda: self.entry.focus_set())
        
        self.btn_ok = ctk.CTkButton(self, text="OK", command=self._potvrdit, width=100, height=35)
        self.btn_ok.pack(pady=20)
        
        # Bind klávesy Enter
        self.bind("<Return>", lambda event: self._potvrdit())
        
        # --- ROBUSTNÍ CENTROVÁNÍ ---
        try:
            self.update_idletasks()
            
            w = 300
            h = 180
            
            # Získáme ABSOLUTNÍ souřadnice rodiče na obrazovce
            # (winfo_rootx je spolehlivější než winfo_x pro Toplevel okna)
            parent_x = parent.winfo_rootx()
            parent_y = parent.winfo_rooty()
            parent_w = parent.winfo_width()
            parent_h = parent.winfo_height()
            
            # Výpočet středu
            x = parent_x + (parent_w // 2) - (w // 2)
            y = parent_y + (parent_h // 2) - (h // 2)
            
            # Pojistka proti záporným souřadnicím (mimo obrazovku)
            if x < 0: x = 0
            if y < 0: y = 0
            
            self.geometry(f"{w}x{h}+{x}+{y}")
            
        except Exception as e:
            # Kdyby výpočet selhal, dáme to prostě na střed obrazovky
            print(f"Chyba centrování hesla: {e}")
            self.geometry("300x180")
            self.eval('tk::PlaceWindow . center')

        # Zobrazíme okno
        self.deiconify()
        
        # Vynutíme, aby toto okno bylo aktivní
        self.lift()
        self.focus_force()
        
        # Modální okno (zablokuje klikání jinam)
        self.grab_set()
        self.wait_window()

    def _potvrdit(self):
        self.password = self.entry.get()
        self.destroy()

    def get_input(self):
        return self.password
    
class SettingsManager:
    def __init__(self, filename="nastaveni_AGCGlueControl.json"):
        self.filename = filename
        
        self.DEFAULT_CONFIG = {
            "line": "N/A",              
            "project": "N/A",           
            "usl": 5.0,                 
            "lsl": 3.0,                 
            "target": 4.0,              
            "timer_minutes": 240,       
            "appearance_mode": "Dark",  
            "color_theme": "blue",       
            "show_seconds": False,
            "language": "EN"       
        }
        
        self.data = self.load_config()

    def load_config(self):
        if not os.path.exists(self.filename):
            self.save_config(self.DEFAULT_CONFIG)
            return self.DEFAULT_CONFIG
        
        try:
            with open(self.filename, "r", encoding="utf-8-sig") as f:
                loaded = json.load(f)
                for key, val in self.DEFAULT_CONFIG.items():
                    if key not in loaded:
                        loaded[key] = val
                return loaded
        except:
            return self.DEFAULT_CONFIG

    def save_config(self, data=None):
        if data:
            self.data = data
        try:
            with open(self.filename, "w", encoding="utf-8-sig") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Chyba ukládání: {e}")

    def get(self, key, default=None):
        return self.data.get(key, self.DEFAULT_CONFIG.get(key, default))

    def set(self, key, value):
        self.data[key] = value
        self.save_config()

class ModelSetupDialog(ctk.CTkToplevel):
    def __init__(self, parent, edit_model=None):
        super().__init__(parent)
        if edit_model is not None:
            self.withdraw()  # Skryjeme okno během inicializace
        t = TEXTS[parent.jazyk]
        self.parent = parent
        self.edit_model = edit_model
        
        
        # Titulek
        titulek = t["edit_model_limits"] if edit_model else t["model_setup_title"]
        self.title(titulek)
        
        self.parent.umistit_okno_na_obrazovce(self, 350, 550, typ_okna="nastaveni")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.grab_set()
        
        self.dostupne_modely = self.parent.nacist_znacky()
        self.existujici_modely = self._ziskat_seznam_modelu()
        # Defaultní hodnoty
        val_usl = self.parent.usl
        val_target = self.parent.target
        val_lsl = self.parent.lsl
        val_timer = self.parent.shift_duration // 60
        
        val_ucl = ""
        val_lcl = ""
        self.ma_pevne_limity = False

        # --- NAČTENÍ DAT PŘI EDITACI ---
        if self.edit_model:
            found_data = self._nacist_data_z_csv(self.edit_model)
            if found_data:
                val_usl = found_data["USL"]
                val_target = found_data["Target"]
                val_lsl = found_data["LSL"]
                val_timer = found_data["Timer"]
                raw_ucl = found_data.get("UCL", "")
                raw_lcl = found_data.get("LCL", "")

                if raw_ucl != "" and raw_lcl != "":
                    val_ucl = raw_ucl
                    val_lcl = raw_lcl
                    self.ma_pevne_limity = True

        # --- GUI ---
        self.frame = ctk.CTkFrame(self)
        self.frame.pack(fill="both", expand=True, padx=20, pady=20)
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.frame, text=titulek, font=("Arial", 20, "bold")).grid(column=0, row=0, pady=20, columnspan=2)

        # --- ROZHODOVÁNÍ: NOVÝ vs. EDITACE ---
        
        if self.edit_model:
            # === REŽIM EDITACE: JEN LABEL ===
            # Zobrazíme název modelu jako statický text
            ctk.CTkLabel(self.frame, text="Model:", font=("Arial", 14)).grid(column=0, row=1, sticky="w", padx=15, pady=5)
            
            lbl_name = ctk.CTkLabel(self.frame, text=self.edit_model, font=("Arial", 18, "bold"), text_color="#3B8ED0")
            lbl_name.grid(column=1, row=1, sticky="w", padx=0, pady=5)
            
        else:
            # === REŽIM NOVÝ: VSTUPNÍ POLE ===
            # 1. Značka
            ctk.CTkLabel(self.frame, text=t["select_car"]).grid(column=0, row=1, sticky="w", padx=(15,0), pady=5)
            self.option_model = ctk.CTkOptionMenu(self.frame, values=self.dostupne_modely, width=150)
            self.option_model.grid(column=1, row=1, padx=0, pady=5, sticky="w")
            self.option_model.set(self.dostupne_modely[0] if self.dostupne_modely else "N/A")
            
            # 2. Typ
            ctk.CTkLabel(self.frame, text=t["select_model"]).grid(column=0, row=2, sticky="w", padx=15, pady=5)
            self.entry_specific_model = ctk.CTkEntry(self.frame, width=150, placeholder_text=t["select_model_example"])    
            self.entry_specific_model.grid(column=1, row=2, padx=0, pady=5, sticky="w")


        # 3. LIMITY (Společné pro oba režimy)
        # Posuneme řádkování dolů (row=3 a dál)
        self.entry_usl = self._add_input(t["usl"], 3, val_usl, unit="g")
        self.entry_target = self._add_input(t["target"], 4, val_target, unit="g")
        self.entry_lsl = self._add_input(t["lsl"], 5, val_lsl, unit="g")

        self.entry_timer = self._add_input(t["timer_minutes"], 6, val_timer, unit="min")

        ctk.CTkFrame(self.frame, height=2, fg_color="gray50").grid(row=7, column=0, columnspan=2, sticky="ew", pady=15)
        self.var_pevne_limity = ctk.BooleanVar(value=self.ma_pevne_limity)
        self.chk_pevne = ctk.CTkCheckBox(
            self.frame, 
            text=t["fixed_limits"], 
            variable=self.var_pevne_limity,
            command=self.prepni_spc_vstupy, # Při kliknutí se odemknou/zamknou
            font=("Arial", 12, "bold")
        )
        self.chk_pevne.grid(row=7, column=0, columnspan=2, sticky="w", padx=15, pady=5)
        
        if self.edit_model and self.ma_pevne_limity:
            self.chk_pevne.configure(state="disabled") # Uživatel nemůže checkbox odškrtnout
            self.chk_pevne.configure(text=t["fixed_limits_enabled"]) # Změníme text, aby bylo jasné, že jsou pevné limity povoleny

        self.entry_ucl = self._add_input("UCL", 8, val_ucl, unit="g")
        self.entry_lcl = self._add_input("LCL", 9, val_lcl, unit="g")

        self.prepni_spc_vstupy()

        # TLAČÍTKO
        btn_text = t["save_changes"] if self.edit_model else t["save_new_model"]
        self.btn_save = ctk.CTkButton(self.frame, text=btn_text, command=self.ulozit_model, height=50, font=("Arial", 16, "bold"))
        self.btn_save.grid(column=0, row=12, columnspan=2, pady=30, padx=15, sticky="ew")

        self.deiconify() 

    def _ziskat_limity_z_historie(self, model_name):
        """
        Prohledá soubor s naměřenými daty (spc_data.csv) a najde poslední
        použité limity (USL, Target, LSL) pro daný model.
        """
        posledni_zaznam = None
        
        try:
            with open(self.parent.cesta_data, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f, delimiter=';')
                for row in reader:
                    # Hledáme shodu jména modelu
                    if row.get("Model") == model_name and row.get("Linka") == self.parent.current_set_line:
                        posledni_zaznam = row
                        
                        # Pokračujeme ve čtení až do konce, abychom měli ten NEJNOVĚJŠÍ
        except Exception:
            return None # Soubor neexistuje nebo chyba čtení
        
        if posledni_zaznam:
            try:
                # Vrátíme slovník s čísly. UCL/LCL v historii nebývají, jen tolerance.
                return {
                    "USL": float(posledni_zaznam["Limit_USL"].replace(",", ".")),
                    "Target": float(posledni_zaznam["Target"].replace(",", ".")),
                    "LSL": float(posledni_zaznam["Limit_LSL"].replace(",", "."))
                }
            except (ValueError, KeyError):
                return None # Data byla poškozená
        
        return None

    def _ziskat_seznam_modelu(self):
        """Přečte CSV modely_spc a vrátí seznam názvů modelů pro aktuální linku."""
        jmena_modelu = []
        try:
            with open(self.parent.cesta_modely, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f, delimiter=';')
                for row in reader:
                    # Zajímá nás jen model na aktuální lince
                    if row["Linka"] == self.parent.current_set_line:
                        jmena_modelu.append(row["Model"])
        except Exception:
            # Pokud soubor neexistuje nebo je chyba, vrátíme prázdný seznam
            return []
        return jmena_modelu

    def prepni_spc_vstupy(self):
        """Odemkne nebo zamkne vstupy pro UCL/LCL podle checkboxu."""
        is_active = self.var_pevne_limity.get()
        state = "normal" if is_active else "disabled"
        if is_active:
            bg_color = ("#F9F9FA", "#343638") 
        else:
            bg_color = ("gray85", "gray25")
        
        self.entry_ucl.configure(state=state, fg_color=bg_color)
        self.entry_lcl.configure(state=state, fg_color=bg_color)
        if not is_active:
             self.entry_ucl.delete(0, tk.END)
             self.entry_lcl.delete(0, tk.END)
             self.entry_ucl.configure(placeholder_text="Auto")
             self.entry_lcl.configure(placeholder_text="Auto")
        else:
             self.entry_ucl.configure(placeholder_text="")
             self.entry_lcl.configure(placeholder_text="")
        

    def ziskat_heslo(self):
        """Vytvoří vlastní okno pro zadání hesla se skrytým textem."""
        vysledek = {"heslo": None} 

        dialog = ctk.CTkToplevel(self.parent)
        dialog.title("Ověření")
        dialog.geometry("300x180")
        dialog.attributes("-topmost", True)
        # Odstraníme minimalizaci/maximalizaci pro čistší vzhled (volitelné)
        dialog.resizable(False, False) 
        dialog.grab_set()
        
        # Výpočet středu vůči RODIČI (self.parent)
        dialog.update_idletasks()
        parent_x = self.parent.winfo_x()
        parent_y = self.parent.winfo_y()
        parent_width = self.parent.winfo_width()
        parent_height = self.parent.winfo_height()
        dialog.parent.umistit_okno_na_obrazovce(dialog, 300, 180)

        

        label = ctk.CTkLabel(dialog, text="Zadejte heslo pro úpravu:", font=("Arial", 14))
        label.pack(pady=(20, 10))

        entry = ctk.CTkEntry(dialog, show="*", width=200)
        entry.pack(pady=10)

        # Focus triky pro spolehlivé aktivování kurzoru
        dialog.focus_force()
        entry.focus_set()
        
        def potvrdit(event=None):
            vysledek["heslo"] = entry.get()
            dialog.destroy()

        btn = ctk.CTkButton(dialog, text="OK", command=potvrdit, width=100)
        btn.pack(pady=20)

        entry.bind("<Return>", potvrdit)

        # Čekáme, dokud uživatel okno nezavře
        self.parent.wait_window(dialog)
        return vysledek["heslo"]
    
    def _nacist_data_z_csv(self, model_name):
        try:
            with open(self.parent.cesta_modely, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f, delimiter=';')
                for row in reader:
                    if row["Model"] == model_name and row["Linka"] == self.parent.current_set_line:
                        return {
                            "USL": float(row["USL"].replace(",", ".")),
                            "LSL": float(row["LSL"].replace(",", ".")),
                            "Target": float(row["Target"].replace(",", ".")),
                            "Timer": int(row.get("Timer", "240")),
                            "UCL": float(row.get("UCL", "0").replace(",", ".")),
                            "LCL": float(row.get("LCL", "0").replace(",", "."))

                        }
        except Exception as e:
            print(f"Edit load error: {e}")
        return None

    def _add_input(self, text, row, value, unit=None):
        ctk.CTkLabel(self.frame, text=text).grid(column=0, row=row, sticky="w", padx=15, pady=5)
        if unit:
            container = ctk.CTkFrame(self.frame, fg_color="transparent")
            container.grid(column=1, row=row, padx=0, pady=5, sticky="w")
            entry = ctk.CTkEntry(container, width=80) 
            entry.pack(side="left")
            ctk.CTkLabel(container, text=unit).pack(side="left", padx=(5, 0))
        elif text == "UCL" or text == "LCL":
            entry = ctk.CTkComboBox(self.frame, width=150)
            entry.grid(column=1, row=row, padx=0, pady=5, sticky="w")
        else:
            entry = ctk.CTkEntry(self.frame, width=150)
            entry.grid(column=1, row=row, padx=0, pady=5, sticky="w")
        
        entry.insert(0, str(value))
        return entry

    def ulozit_model(self):
        t= TEXTS[self.parent.jazyk]
        
            
        try:
            # --- ZÍSKÁNÍ JMÉNA MODELU ---
            if self.edit_model:
                # Jednoduché: Pokud editujeme, jméno už známe a nemění se
                model = self.edit_model
            else:
                # Složitější: Pokud tvoříme nový, musíme ho poskládat
                typ = self.entry_specific_model.get().strip()
                if not typ:
                    messagebox.showerror(t["error"], t["choose_model_type"], parent=self)
                    return
                znacka = self.option_model.get()
                model = f"{znacka} {typ}"
            
            if model in self.existujici_modely and not self.edit_model:
                messagebox.showerror(t["error"], t["model_exists"], parent=self)
                return
            
            if not self.edit_model:
                historie = self._ziskat_limity_z_historie(model)

                if historie:
                    # Načteme aktuální hodnoty z okének
                    try:
                        c_usl = float(self.entry_usl.get().replace(",", "."))
                        c_tar = float(self.entry_target.get().replace(",", "."))
                        c_lsl = float(self.entry_lsl.get().replace(",", "."))
                    except ValueError:
                        c_usl, c_tar, c_lsl = -999, -999, -999

                    # Porovnání
                    diff = (abs(c_usl - historie["USL"]) > 0.0001 or
                            abs(c_tar - historie["Target"]) > 0.0001 or
                            abs(c_lsl - historie["LSL"]) > 0.0001)

                    if diff:
                        msg_found = t["history_found_msg"].format(model=model)
                        zprava = (
                            f"{msg_found}\n"
                            f"{t['history_differs']}\n\n"
                            f"{t['history_vs_input']}:\n"
                            f"USL:    {historie['USL']}  vs  {self.entry_usl.get()}\n"
                            f"Target: {historie['Target']}  vs  {self.entry_target.get()}\n"
                            f"LSL:    {historie['LSL']}  vs  {self.entry_lsl.get()}\n\n"
                            f"{t['load_history_q']}"
                        )
                        
                        if messagebox.askyesno(t["history_title"], zprava, parent=self):
                            self.entry_usl.delete(0, "end")
                            self.entry_usl.insert(0, str(historie["USL"]))
                            self.entry_target.delete(0, "end")
                            self.entry_target.insert(0, str(historie["Target"]))
                            self.entry_lsl.delete(0, "end")
                            self.entry_lsl.insert(0, str(historie["LSL"]))
                            
                            messagebox.showinfo(t["values_loaded_title"], t["values_loaded_msg"], parent=self)
                            return # Zastavíme ukládání, aby si to uživatel zkontroloval

            # --- ZÍSKÁNÍ ČÍSEL ---
            usl = float(self.entry_usl.get().replace(",", "."))
            target = float(self.entry_target.get().replace(",", "."))
            lsl = float(self.entry_lsl.get().replace(",", "."))
            timer = int(self.entry_timer.get())
            ucl_final = ""
            lcl_final = ""

            # Validace
            if lsl >= usl:
                messagebox.showerror(t["warning"], t["lsl_less_than_usl"], parent=self)
                return
            if not (lsl < target < usl):
                messagebox.showerror(t["warning"], t["target_between_lsl_usl"], parent=self)
                return

            if self.var_pevne_limity.get():
                # Uživatel chce pevné limity -> Musí být vyplněné
                raw_ucl = self.entry_ucl.get().replace(",", ".").strip()
                raw_lcl = self.entry_lcl.get().replace(",", ".").strip()
                
                if not raw_ucl or not raw_lcl:
                    messagebox.showerror(t["warning"], t["fill_ucl_lcl"], parent=self)
                    return
                val_ucl = float(raw_ucl)
                val_lcl = float(raw_lcl)

                if val_lcl >= val_ucl:
                    messagebox.showerror(t["warning"], t["lcl_less_than_ucl"], parent=self)
                    return
            
                if not (val_lcl < target < val_ucl):
                    messagebox.showerror(t["warning"], t["target_between_lcl_ucl"], parent=self)
                    return
                varovani= []
                if val_lcl <= lsl:
                    varovani.append(t["lcl_below_lsl"])
                    
                if val_ucl >= usl:
                    varovani.append(t["ucl_above_usl"])
                if varovani:
                    # Spojíme odrážky a přidáme otázku, zda pokračovat
                    souhrn_varovani = "\n".join(varovani)
                    text_dotazu = f"{souhrn_varovani}\n\n{t['proceed_anyway']}"
                    
                    # Titulek okna bude t["warning"], obsah text_dotazu
                    if not messagebox.askyesno(t["warning"], text_dotazu, parent=self):
                        return # Uživatel zvolil "Ne", vracíme se k opravě
                
                # Pokud projdeme až sem, nastavíme finální hodnoty pro uložení
                ucl_final = raw_ucl
                lcl_final = raw_lcl
            else:
                ucl_final = ""
                lcl_final = ""
            if not self.edit_model and model in self.existujici_modely:
                if not messagebox.askyesno(t["confirm"], t["name_cant_be_changed"], parent=self):
                    return
            if self.edit_model:
                if not messagebox.askyesno(t["confirm"], t["timer_will_reset"], parent=self):
                    return
            # 1. Zápis do databáze (přepíše existující nebo přidá nový)
            self.parent.aktualizovat_databazi_modelu(model, self.parent.current_set_line, usl, lsl, target, timer, ucl_final, lcl_final)

            # 2. Pokud upravujeme model, který je ZROVNA AKTIVNÍ, aktualizujeme běžící aplikaci
            # NEBO pokud vytváříme nový model, rovnou ho aktivujeme
            is_current_active = (model == self.parent.aktualni_model)
            is_new_model = (not self.edit_model)

            if is_current_active or is_new_model:
                self.parent.settings.set("project", model)
                self.parent.settings.set("usl", usl)
                self.parent.settings.set("lsl", lsl)
                self.parent.settings.set("target", target)
                self.parent.settings.set("timer_minutes", timer)
                
                self.parent.aktualni_model = model
                self.parent.usl = usl
                self.parent.lsl = lsl
                self.parent.target = target
                self.parent.shift_duration = timer * 60
                self.parent.timer_seconds = self.parent.shift_duration
                self.parent.aktualni_smena = "N/A"

                t_main = TEXTS[self.parent.jazyk]
                novy_text_smeny = t_main["current_shift"].format(shift_name="N/A")
                self.parent.lbl_smena_info.configure(text=novy_text_smeny)
                # Reset grafu
                self.parent.ax = None 
                for widget in self.parent.graph_frame.winfo_children():
                    widget.destroy()
                
                self.parent.init_graph()
                self.parent.zmena_modelu(model)
                self.parent.lbl_model_display.configure(text=model)

            # 3. Refresh tlačítek
            self.parent.refresh_model_buttons()
            self.parent.reset_timer(typ="rozjezd")
            self.destroy()

        except ValueError:
             messagebox.showerror(t["error"], "Zadejte platná čísla!", parent=self)
        
        

class InputDialog(ctk.CTkToplevel):
    def __init__(self, parent, zpusob_otevreni=None):
        t = TEXTS[parent.jazyk]
        super().__init__(parent)
        self.parent = parent
        self.title(t["input_dialog_title"])
        self.parent.umistit_okno_na_obrazovce(self, 400, 500, typ_okna="measurement_dialog")
        self.attributes("-topmost", True)
        self.grab_set()

        self.zpusob_otevreni = zpusob_otevreni
        self.texts = TEXTS[parent.jazyk]
        self.parent.operator_names = self.parent.spravovat_operatory()
        self.puvodni_barva = self.cget("fg_color")
        self.blink_on = False
        self.blikani_id = None

        def load_scale_icon(name_black, name_white):
            try:
                # Použijeme resource_path z rodiče (self.parent)
                path_black = self.parent.resource_path(f"icons/{name_black}")
                path_white = self.parent.resource_path(f"icons/{name_white}")
                
                return ctk.CTkImage(
                    light_image=Image.open(path_black),
                    dark_image=Image.open(path_white),
                    size=(26, 26) # Velikost ikonky
                )
            except Exception as e:
                print(f"Varování: Ikona váhy nebyla nalezena. ({e})")
                return None
        icon_bt = load_scale_icon("weight_white.png", "weight_black.png")    
        ctk.CTkLabel(self, text=self.texts["alert_title"], font=("Arial", 24, "bold")).place(relx=0.5, rely=0.07, anchor="center")
        
        # 1. OPERÁTOR
        ctk.CTkLabel(self, text=self.texts["lbl_operator"]).place(relx=0.5, rely=0.16, anchor="center")
        self.option_operator = ctk.CTkOptionMenu(self, values=self.parent.operator_names, width=200, height=40)
        self.option_operator.place(relx=0.5, rely=0.24, anchor="center")
        if hasattr(self.parent, "aktualni_operator") and self.parent.aktualni_operator:
             if self.parent.aktualni_operator in self.parent.operator_names:
                 self.option_operator.set(self.parent.aktualni_operator)
        
        # 2. VÝBĚR SMĚNY
        ctk.CTkLabel(self, text=self.texts.get("lbl_shift"+":", "Směna")).place(relx=0.5, rely=0.32, anchor="center")
        self.option_shift = ctk.CTkOptionMenu(self, values=["A", "B", "C", "D"], width=200, height=40)
        self.option_shift.place(relx=0.5, rely=0.39, anchor="center")
        self.option_shift.set(self.parent.aktualni_smena)
        
        # 3. HODNOTA bez lepidla
        ctk.CTkLabel(self, text=self.texts["lbl_value_without_glue"]).place(relx=0.5, rely=0.48, anchor="center")
        self.entry_value = ctk.CTkEntry(self, placeholder_text="0.00", font=("Arial", 30), width=200)
        self.entry_value.place(relx=0.5, rely=0.55, anchor="center")
        self.entry_value.focus()
        
        # 4. hodnota s lepidlem
        ctk.CTkLabel(self, text=self.texts["lbl_value_with_glue"]).place(relx=0.5, rely=0.64, anchor="center")
        self.entry_value_with_glue = ctk.CTkEntry(self, placeholder_text="0.00", font=("Arial", 30), width=200)
        self.entry_value_with_glue.place(relx=0.5, rely=0.71, anchor="center")
        self.entry_value_with_glue.configure(state="disabled")
        self.entry_value_with_glue.focus()

        # Tlačítka
        self.btn_bt_no_glue = ctk.CTkButton(self, image=icon_bt, text="", command=self.read_scale_no_glue_testing, height=40, width=50, font=("Arial", 18, "bold"))
        self.btn_bt_no_glue.place(relx=0.84, rely=0.55, anchor="center")
        self.btn_bt_with_glue = ctk.CTkButton(self, image=icon_bt, text="", command=self.read_scale_with_glue_testing, height=40, width=50, font=("Arial", 18, "bold"))
        self.btn_bt_with_glue.place(relx=0.84, rely=0.71, anchor="center")
        self.btn_bt_with_glue.configure(state="disabled")

        self.btn_save = ctk.CTkButton(self, text=self.texts["btn_save"], command=self.save_and_close, height=50, font=("Arial", 18, "bold"), width=200)
        self.btn_save.place(relx=0.5, rely=0.87, anchor="center")
        
        self.bind("<Button-1>", self._zastavit_blikani)
        self.entry_value.bind("<Button-1>", self._zastavit_blikani, add="+")
        self.entry_value_with_glue.bind("<Button-1>", self._zastavit_blikani, add="+")

        self.bind("<Return>", lambda e: self.save_and_close())
        if self.zpusob_otevreni == "timer_expired":
                self._spustit_alarm()

    def _spustit_alarm(self, barva1="yellow", barva2=None):
        """
        Nastartuje cyklus blikání pozadí okna.
        barva1: Barva upozornění (např. oranžová/žlutá)
        barva2: Původní barva (pokud None, vezme se self.puvodni_barva)
        """
        if barva2 is None:
            barva2 = self.puvodni_barva

        def cyklus():
            if not self.winfo_exists(): # Kontrola, zda okno ještě žije
                return
            
            self.blink_on = not self.blink_on
            nova_barva = barva1 if self.blink_on else barva2
            
            # Změníme barvu pozadí celého okna
            self.configure(fg_color=nova_barva)
            
            # Rekurzivní volání přes after
            self.blikani_id = self.after(500, cyklus)
        self.blikani_id = True
        cyklus()
        

    def _zastavit_blikani(self, event=None):
        """Zastaví cyklus blikání a vrátí původní barvu."""
        if hasattr(self, "blikani_id") and self.blikani_id:
            self.after_cancel(self.blikani_id)
            self.blikani_id = None
            # Vrátíme původní barvu pozadí
            self.configure(fg_color=self.puvodni_barva)
     
    def _zavrit_dialog(self):
        """Korektní ukončení dialogu a zastavení timerů."""
        if self.blikani_id:
            self.after_cancel(self.blikani_id)
        self.grab_release()
        self.destroy()

    #def save_and_close(self):
        # ... tvoje logika uložení ...
    #   self._zavrit_dialog()

    def _ziskat_vahu_z_portu(self):
        """
        Pokusí se připojit k váze a přečíst hodnotu.
        Vrací float (váhu) nebo None při chybě.
        """
        # NASTAVENÍ PORTU (Tohle by ideálně mělo být v globálním nastavení)
        # Zjistíš ve Správci zařízení ve Windows (Porty COM a LPT)
        PORT = port_PC_pro_kabel_vahy  # <-- ZMĚŇ PODLE SVÉHO PC (např. COM4, COM5)
        BAUDRATE = 9600 # Standard pro většinu vah (nebo 4800, 19200)
        
        vaha = None
        try:
            # Otevřeme port s timeoutem 1 sekunda (aby to nezaseklo program)
            with serial.Serial(PORT, BAUDRATE, timeout=1) as ser:
                
                # Pokud váha potřebuje příkaz k odeslání, odkomentuj toto:
                # ser.write(b'P\r\n') # Příklad příkazu "Print"
                
                # Přečteme řádek dat z váhy
                raw_data = ser.readline()
                
                # Dekódujeme z bytů na text (utf-8 nebo ascii)
                text_data = raw_data.decode('utf-8-sig', errors='ignore').strip()
                
                print(f"Data z váhy (raw): {text_data}") # Debug výpis do konzole
                
                if not text_data:
                    messagebox.showwarning("Váha", "Váha neodpovídá (žádná data).", parent=self)
                    return None

                # --- PARSOVÁNÍ ČÍSLA (REGEX) ---
                # Hledáme číslo (např. z textu "ST, +  150.2 g")
                # Tento regex najde číslo s desetinnou tečkou
                match = re.search(r"[-+]?\d*\.\d+|\d+", text_data)
                
                if match:
                    vaha = float(match.group())
                    return vaha
                else:
                    messagebox.showerror("Chyba", f"Nepodařilo se přečíst číslo z: {text_data}", parent=self)
                    return None

        except serial.SerialException as e:
            messagebox.showerror("Chyba připojení", f"Nelze otevřít port {PORT}.\n\nJe kabel zapojen?\nChyba: {e}", parent=self)
            return None
        except Exception as e:
            messagebox.showerror("Chyba", f"Neočekávaná chyba: {e}", parent=self)
            return None

    def read_scale_no_glue(self):
        # Načteme váhu z kabelu
        namerena_vaha = self._ziskat_vahu_z_portu()
        
        if namerena_vaha is not None:
            # Pokud se to povedlo, zapíšeme do políčka
            self.entry_value.delete(0, "end")
            self.entry_value.insert(0, str(namerena_vaha))
            
            # Odemkneme další krok
            self.entry_value_with_glue.configure(state="normal")
            self.btn_bt_with_glue.configure(state="normal")
            self.entry_value_with_glue.focus()
            
            # Zastavíme blikání, protože uživatel něco udělal
            self._zastavit_blikani()

    def read_scale_no_glue_testing(self):
        # 1. Vygenerujeme náhodnou váhu čistého dílu (TÁRA)
        # Dejme tomu, že díl váží cca 150g (uprav si dle reality)
        # Pokud vážíš jen lepidlo na vynulované váze, dej sem 0.
        zakladni_vaha_dilu = 150.0 
        
        # Přidáme malý šum, ať to není pořád stejné (+- 2g)
        simulated_weight = round(random.uniform(zakladni_vaha_dilu - 2.0, zakladni_vaha_dilu + 2.0), 2)
        
        # Odemkneme a zapíšeme
        self.entry_value_with_glue.configure(state="normal")
        self.btn_bt_with_glue.configure(state="normal")
        self.entry_value.delete(0, tk.END)
        self.entry_value.insert(0, str(simulated_weight))

    def read_scale_with_glue(self):
        # Načteme váhu z kabelu
        namerena_vaha = self._ziskat_vahu_z_portu()
        
        if namerena_vaha is not None:
            self.entry_value_with_glue.delete(0, "end")
            self.entry_value_with_glue.insert(0, str(namerena_vaha))
            self._zastavit_blikani()

    def read_scale_with_glue_testing(self):
        # 1. Nejdřív musíme zjistit, kolik vážil díl BEZ lepidla
        try:
            val_no_glue_str = self.entry_value.get().replace(",", ".")
            val_no_glue = float(val_no_glue_str)
        except ValueError:
            # Pokud je první políčko prázdné, vymyslíme si ho
            val_no_glue = 150.0
            self.entry_value.delete(0, tk.END)
            self.entry_value.insert(0, str(val_no_glue))

        # 2. Vygenerujeme NÁNOST LEPIDLA, který je přesně mezi LSL a USL
        # self.parent.lsl a usl jsou limity lepidla (např. 0.58 a 0.9)
        lsl = self.parent.lsl
        usl = self.parent.usl
        
        # Vygenerujeme náhodné lepidlo v tomto rozmezí
        nahodne_lepidlo = random.uniform(lsl, usl)
        
        # 3. Sečteme to dohromady (Díl + Lepidlo)
        final_weight = round(val_no_glue + nahodne_lepidlo, 2)
        
        # Zapíšeme
        self.entry_value_with_glue.delete(0, tk.END)
        self.entry_value_with_glue.insert(0, str(final_weight))

    def save_and_close(self):
        t = TEXTS[self.parent.jazyk]
        nepovolene_smeny = ["N/A"]
        
        try:
            raw_no_glue = self.entry_value.get().replace(",", ".")
            raw_with_glue = self.entry_value_with_glue.get().replace(",", ".")

            if not raw_no_glue or not raw_with_glue:
                messagebox.showwarning(t["alert_error"], t["error_both_weights_required"], parent=self)
                return
            val_no_glue = float(raw_no_glue)
            val_with_glue = float(raw_with_glue)
            
            operator = self.option_operator.get()
            smena = self.option_shift.get()
            print(f"Zvoleno: Operátor={operator}, Směna={smena}, Váha bez lepidla={val_no_glue}, Váha s lepidlem={val_with_glue}") # Debug výpis
            if smena in nepovolene_smeny:
                messagebox.showwarning(t["alert_title_shift"], t["shift_warning_message"], parent=self)
                return

            vaha_lepidla = val_with_glue - val_no_glue         
            
            self.parent.aktualni_operator = operator
            self.parent.aktualni_smena = smena
            try:
                novy_text = t["current_shift"].format(shift_name=smena)
                self.parent.lbl_smena_info.configure(text=novy_text)
            except AttributeError:
                print("Nenalezeno!")

            self.parent.add_record(vaha_lepidla, operator, smena)
            
            self.parent.reset_timer(typ="standard")

            self.destroy()

        except ValueError:
            self.entry_value.configure(border_color="red") 
            self.entry_value_with_glue.configure(border_color="red")
            messagebox.showerror(t["alert_error"], t["error_invalid_numbers"], parent=self)

class SPCApp(ctk.CTk):
    def __init__(self):
        # --- 1. CESTY A SLOŽKY ---
        if getattr(sys, 'frozen', False):
            self.base_path = os.path.dirname(sys.executable)
        else:
            self.base_path = os.path.dirname(os.path.abspath(__file__))

        self.config_folder = os.path.join(self.base_path, "SPC_Config")
        self.archive_folder = os.path.join(self.config_folder, "Archiv") # Složka pro zálohy
        
        if not os.path.exists(self.config_folder):
            try: os.makedirs(self.config_folder)
            except: pass
        if not os.path.exists(self.archive_folder):
             try: os.makedirs(self.archive_folder)
             except: pass

        self.cesta_nastaveni = os.path.join(self.config_folder, "nastaveni_AGCGlueControl.json")
        self.cesta_operatori = os.path.join(self.config_folder, "jmena_operatoru.csv")
        self.cesta_modely = os.path.join(self.config_folder, "modely_spc.csv")
        self.cesta_data = os.path.join(self.base_path, "spc_data.csv") 
        self.cesta_znacky = os.path.join(self.config_folder, "znacky_aut.csv")
        
        # --- 2. ARCHIVACE DAT (NOVÉ) ---
        # Provede se ještě před načtením dat
        self.kontrola_a_archivace_dat()

        # --- 3. NAČTENÍ NASTAVENÍ (MUST BE FIRST) ---
        self.settings = SettingsManager(filename=self.cesta_nastaveni)

        # Aplikace vzhledu HNED TEĎ
        saved_appearance = self.settings.get("appearance_mode")
        saved_theme =  self.settings.get("color_theme")
        ctk.set_appearance_mode(saved_appearance if saved_appearance else "Dark")
        ctk.set_default_color_theme(saved_theme if saved_theme else "blue")

        # Načtení klíčových proměnných
        self.current_set_line = self.settings.get("line")
        self.usl = float(self.settings.get("usl"))
        self.lsl = float(self.settings.get("lsl"))
        self.target = float(self.settings.get("target"))
        self.shift_duration = self.settings.get("timer_minutes") * 60
        self.timer_seconds = self.shift_duration
        self.zobrazit_sekundy = self.settings.get("show_seconds")
        self.LIMIT_PRO_UCL_FIX = pocet_pro_ucl_lcl_fix_v_pripade_vypocitanych_control_limitu
        
        # Jazyk
        loaded_lang = self.settings.get("language")
        self.jazyk = loaded_lang if loaded_lang in TEXTS else "CZ"

        # --- 4. INICIALIZACE OKNA ---
        super().__init__()
        self.bind("<Map>", self._oprava_vykreslovani)  # Oprava vykreslování při minimalizaci/maximalizaci
        ctk.deactivate_automatic_dpi_awareness()
        self.umistit_okno_na_obrazovce(self, 1800, 900, typ_okna="hlavni_okno")
        self.title("SPC Monitor")

        # --- 5. ZBYTEK LOGIKY ---
        self.vytvorit_seznam_znacek()
        self.operator_names = self.spravovat_operatory()
        self.operators = json.loads(OPERATORS_JSON)
        if not self.operator_names:
             self.operator_names = [f"{o['id']} - {o['name']}" for o in self.operators]
        self.aktualni_operator = self.operator_names[0] if self.operator_names else "Neznámý"

        self.aktualni_smena = "N/A"
        #uložení typu časovače (pro obnovení při změně modelu)
        self.timer_running = None  # Tady budeme ukládat ID úlohy
        self.timer_seconds = 0

        # Modely
        self.models = ["Default"] 
        if not os.path.exists(self.cesta_modely):
            self.vytvorit_soubor_s_modely()
        nactene_modely = self.ziskat_modely_z_csv()
        if nactene_modely: self.models = nactene_modely

        saved_project = self.settings.get("project")
        if saved_project and saved_project in self.models:
            # Super, model existuje, nastavíme ho
            self.aktualni_model = saved_project
        else:
            # Model byl asi smazán nebo je to první spuštění -> Nastavíme N/A
            print(f"Uložený model '{saved_project}' nenalezen, resetuji na N/A.")
            self.aktualni_model = "N/A"
            self.settings.set("project", "")
        # Data
        self.df = pd.DataFrame()
        if self.aktualni_model != "N/A":
            self.zmena_modelu(self.aktualni_model)
        else:
            pass

        # Obnovení posledního operátora a směny z historie
        if not self.df.empty:
            try:
                posledni = self.df.iloc[-1]
                if "Operator" in posledni: self.aktualni_operator = posledni["Operator"]
                #if "Smena" in posledni and posledni["Smena"] in ["A", "B", "C", "D"]:
                #    self.aktualni_smena = posledni["Smena"] smazal jsem prozatím, je lepší když je N/A
            except: pass

        # Graf settings
        sns.set_theme(style="darkgrid", rc={"axes.facecolor": "#2b2b2b", "figure.facecolor": "#2b2b2b", "text.color": "white", "xtick.color": "white", "ytick.color": "white"})

        # --- 6. START UI A KONTROLA ---
        self.setup_ui()
        #self.update_timer()
        
        self.after(500, self.kontrola_povinneho_nastaveni)
        self.after(200, self.aktualizovat_semafor)

    def vypocitat_trend_a_status(self):
        """
        Toto je centrální mozek. Počítá trend pro semafor i pro graf.
        Vrací slovník s výsledky.
        """
        t = TEXTS[self.jazyk]
        vysledek = {
            "dostatek_dat": False,
            "barva": "gray",  # Default
            "text": "",
            "slope": 0,
            "intercept": 0,
            "x": None,
            "y": None
        }

        # Pokud nemáme dost dat, končíme
        if self.df is None or self.df.empty or len(self.df) < pocet_pro_ucl_lcl_fix_v_pripade_vypocitanych_control_limitu:
            return vysledek

        try:
            df_history = self.df.tail(250).copy()
            # Převod "0,74" -> 0.74 (text na číslo)
            df_history["Hodnota"] = pd.to_numeric(
                df_history["Hodnota"].astype(str).str.replace(",", "."), 
                errors='coerce'
            )
            df_history = df_history.dropna(subset=["Hodnota"]) # Smazání chyb
            
            if len(df_history) < 2: return vysledek
            
        except Exception as e:
            print(f"Chyba dat: {e}")
            return vysledek     

        # PŘÍPRAVA DAT PRO REGRESI
        y_values = df_history["Hodnota"].values
        x_values = np.arange(len(y_values)) # 0, 1, 2, ... N
        slope, intercept = np.polyfit(x_values, y_values, 1)

        vysledek["dostatek_dat"] = True
        vysledek["slope"] = slope
        vysledek["intercept"] = intercept
        vysledek["x"] = x_values
        vysledek["y"] = y_values

        # --- VYHODNOCENÍ TRENDU ---
        zpravy = []
        barva_statusu = "#00E676" # Zelená (default)

        # Hranice "roviny" - pokud je sklon velmi malý, považujeme to za stabilní
        if abs(slope) < 0.001:
            zpravy.append(t["trend_stable"])
        else:
            trend_text = t["trend_rising"] if slope > 0 else t["trend_falling"]
            zpravy.append(trend_text)

            aktualni_index = len(y_values)
            
            def zkontroluj_naraz(limit, text_klic, je_kriticky):
                nonlocal barva_statusu # Abychom mohli měnit barvu vně této funkce
                
                if slope == 0: return
                
                # Kdy se protnou?
                cilovy_x = (limit - intercept) / slope
                zbyva = cilovy_x - aktualni_index
                
                # Pokud je náraz v budoucnosti a dohledné době (do 400 měření)
                if 0 < zbyva < 400:
                    zprava = t[text_klic].format(n=int(zbyva))
                    zpravy.append(zprava)
                    
                    # LOGIKA SEMAFORU (Priority barev)
                    # Červená má přednost před Oranžovou. Oranžová před Zelenou.
                    
                    if zbyva < 50:
                        if je_kriticky:
                            # Náraz do USL/LSL -> totální stop, červená
                            barva_statusu = "#FF1744" 
                        else:
                            # Náraz do UCL/LCL -> je to blízko, ale pořád jen oranžová
                            if barva_statusu != "#FF1744": # Pokud už tam není červená z USL
                                barva_statusu = "#FF9100" # Červená (Kritické)
                    elif zbyva < 200:
                        # Pokud už je červená, nepřebarvujeme ji na oranžovou!
                        if barva_statusu != "#FF1744":
                            barva_statusu = "#FF9100" # Oranžová (Varování)

            # --- VOLÁNÍ KONTROLY ---
            # Pokud stoupáme -> kontrolujeme horní limity
            if slope > 0:
                # 1. Zkontrolujeme UCL (pokud je nastaveno - varování)
                ucl_val = self.fixed_ucl if hasattr(self, 'fixed_ucl') and self.fixed_ucl else None
                if ucl_val: zkontroluj_naraz(ucl_val, "cross_ucl", False)
                
                # 2. Zkontrolujeme USL (Kritické!)
                zkontroluj_naraz(self.usl, "cross_usl", True)
            
            # Pokud klesáme -> kontrolujeme dolní limity
            else:
                # 1. Zkontrolujeme LCL (pokud je nastaveno - varování)
                lcl_val = self.fixed_lcl if hasattr(self, 'fixed_lcl') and self.fixed_lcl else None
                if lcl_val: zkontroluj_naraz(lcl_val, "cross_lcl", False)

                # 2. Zkontrolujeme LSL (Kritické!)
                zkontroluj_naraz(self.lsl, "cross_lsl", True)

        # 5. Zabalení výsledku
        vysledek["text"] = "\n".join(zpravy)
        vysledek["barva"] = barva_statusu
        
        return vysledek

    def aktualizovat_semafor(self):
        """Metoda, která fyzicky přebarví tečku v horním panelu."""
        if not hasattr(self, 'status_light'):
            return

        try:
            data = self.vypocitat_trend_a_status()
            self.status_light.configure(fg_color=data["barva"])
        except Exception as e:
            print(f"Chyba semaforu: {e}")

    def _oprava_vykreslovani(self, event=None):
        """Vynutí plné vykreslení okna po obnovení z lišty. Kvůli nějaký chybě v CTK."""
        self.attributes("-alpha", 1.0)
        self.update_idletasks()
        
        current_bg = self.cget("fg_color")
        self.configure(fg_color=current_bg)

    def kontrola_a_archivace_dat(self):
        """
        Zkontroluje, zda data nepochází z minulého týdne.
        Pokud ano, vytvoří ZÁLOHU (kopii) do archivu, ale HLAVNÍ DATA NECHÁ BÝT.
        """
        if not os.path.exists(self.cesta_data):
            return

        try:
            # 1. Zjistíme datum poslední úpravy souboru
            timestamp = os.path.getmtime(self.cesta_data)
            last_modified_date = datetime.datetime.fromtimestamp(timestamp)
            current_date = datetime.datetime.now()

            # 2. Získáme čísla týdnů
            # Používám .isocalendar(), který vrací (rok, týden, den)
            last_year, last_week, _ = last_modified_date.isocalendar()
            curr_year, curr_week, _ = current_date.isocalendar()
            
            # Pokud je poslední úprava z jiného (staršího) týdne
            # (Ošetřujeme i přelom roku: pokud je rok jiný, nebo týden jiný)
            je_novy_tyden = (curr_year > last_year) or (curr_week > last_week)

            if je_novy_tyden:
                nazev_zalohy = f"spc_data_{last_year}_Week{last_week}.csv"
                cilova_cesta = os.path.join(self.archive_folder, nazev_zalohy)
                
                # 3. KONTROLA: Pokud záloha ještě neexistuje, vytvoříme ji
                if not os.path.exists(cilova_cesta):
                    shutil.copy2(self.cesta_data, cilova_cesta)
                    print(f"✔ Týdenní záloha vytvořena: {nazev_zalohy}")
                    print("  (Hlavní soubor ponechán pro kontinuitu SPC)")
                else:
                    # Záloha už existuje, takže nic neděláme (abychom ji nepřepsali)
                    pass
                
        except Exception as e:
            print(f"Chyba při archivaci: {e}")

    def vytvorit_seznam_znacek(self):
        """Vytvoří CSV soubor s výrobci, pokud ještě neexistuje."""
        if not os.path.exists(self.cesta_znacky):
            try:
                seznam = [
                    "Alfa Romeo", "Aston Martin", "Audi", 
                    "Bentley", "BMW", "Chevrolet", 
                    "Chrysler", "Citroën", "Cupra", "Dacia", 
                    "DS Automobiles", "Ferrari", "Fiat", "Ford", 
                    "GMC", "Honda", "Hyundai", 
                    "Jaguar", "Jeep", "Kia", "Lamborghini", 
                    "Land Rover", "Lexus", "Mazda", "McLaren", "Mercedes-Benz", "MG", 
                    "Mitsubishi", "Nissan", "Opel", "Peugeot", "Porsche", "Renault", 
                    "Rivian", "SEAT", "Skoda",
                    "SsangYong", "Subaru", "Suzuki", "Tesla", "Toyota", 
                    "Volkswagen", "Volvo"
                ]
                with open(self.cesta_znacky, "w", encoding="utf-8-sig", newline='') as f:
                    writer = csv.writer(f)
                    for znacka in sorted(seznam):
                        writer.writerow([znacka])
                print("Soubor s výrobci byl úspěšně vytvořen.")
            except Exception as e:
                print(f"Chyba při vytváření seznamu značek: {e}")
            
    def nacist_znacky(self):
        seznam = []
        try:
            with open(self.cesta_znacky, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                seznam = [r[0] for r in reader if r]
        except: 
            return ["Default Car"]
        return sorted(seznam)
        
    # --- METODY PRO SOUBORY ---
    def kontrola_povinneho_nastaveni(self):
        t= TEXTS[self.jazyk]
        spatne_hodnoty = ["N/A", "Default", "", t["just_choose"], None]
        je_spatna_linka = self.current_set_line in spatne_hodnoty
        
        if je_spatna_linka:
            messagebox.showinfo(
                "First Time Setup", 
                "Welcome!\n\nBefore the first measurement, it is necessary to select a LINE.\n\nThe settings will now open."
            )
            self.nastaveni_app(vynucene_otevreni=True)

    def spravovat_operatory(self):
        if not os.path.exists(self.cesta_operatori):
            try:
                with open(self.cesta_operatori, "w", encoding="utf-8-sig", newline='') as f:
                    writer = csv.writer(f, delimiter=';')
                    for o in json.loads(OPERATORS_JSON):
                        writer.writerow([f"{o['id']} - {o['name']}"])
            except: pass

        seznam = []
        try:
            with open(self.cesta_operatori, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f, delimiter=';')
                seznam = [row[0] for row in reader if row]
        except:
            seznam = [f"{o['id']} - {o['name']}" for o in json.loads(OPERATORS_JSON)]
        return seznam
    
    def vytvorit_soubor_s_modely(self):
        try:
            with open(self.cesta_modely, mode="w", encoding="utf-8-sig", newline='') as csvfile:
                writer = csv.writer(csvfile, delimiter=';')
                writer.writerow(["Model", "Linka", "USL", "LSL", "Target", "Timer"])
                

        except Exception as e:
            print(f"Chyba modelů: {e}")

    def aktualizovat_databazi_modelu(self, model_nazev, linka_nazev, nove_usl, nove_lsl, nove_target, nove_timer, nove_ucl, nove_lcl):
        temp_data = []
        nasel = False
        
        cesta = self.cesta_modely
        hlavicka = ['Model', 'Linka', 'USL', 'LSL', 'Target', 'Timer', "UCL", "LCL"]

        try:
            with open(cesta, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f, delimiter=';')
                for row in reader:
                    if row['Model'] == model_nazev and row['Linka'] == linka_nazev:
                        row['USL'] = str(nove_usl)
                        row['LSL'] = str(nove_lsl)
                        row['Target'] = str(nove_target)
                        row['Timer'] = str(nove_timer)
                        row['UCL'] = str(nove_ucl)
                        row['LCL'] = str(nove_lcl)
                        nasel = True
                    temp_data.append(row)
        except Exception as e:
            print(f"Chyba čtení modelů: {e}")
            return

        if not nasel:
            temp_data.append({
                "Model": model_nazev,
                "Linka": linka_nazev,
                "USL": str(nove_usl),
                "LSL": str(nove_lsl),
                "Target": str(nove_target),
                "Timer": str(nove_timer),
                "UCL": str(nove_ucl),
                "LCL": str(nove_lcl)
            })

        try:
            with open(cesta, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=hlavicka, delimiter=';')
                writer.writeheader()
                writer.writerows(temp_data)
        except Exception as e:
            print(f"Chyba zápisu modelů: {e}")

    def ziskat_modely_z_csv(self):
        models = set()
        try:
            with open(self.cesta_modely, mode="r", encoding="utf-8-sig") as csvfile:
                reader = csv.DictReader(csvfile, delimiter=';')
                for row in reader:
                    models.add(row["Model"])
            return sorted(list(models))
        except:
            return ["Default"]

    def nacteni_starych_dat_z_csv(self):
        pozadovane_sloupce = ["Datum", "Cas", "Model", "Linka", "Operator", "Smena", "Hodnota", "Limit_USL", "Limit_LSL", "Target", "Status"]
        empty_df = pd.DataFrame(columns=pozadovane_sloupce)
        if not os.path.exists(self.cesta_data):
            return empty_df

        try:
            df_raw = pd.read_csv(self.cesta_data, sep=';', decimal=',', encoding='utf-8-sig', on_bad_lines='skip')
            if df_raw.empty: return empty_df

            if "Model" not in df_raw.columns or "Linka" not in df_raw.columns:
                return empty_df

            maska = (df_raw["Model"] == self.aktualni_model) & (df_raw["Linka"] == self.current_set_line)
            df_filtered = df_raw.loc[maska].copy()

            if df_filtered.empty: return empty_df

            df_filtered["Hodnota"] = pd.to_numeric(df_filtered["Hodnota"], errors='coerce')
            df_filtered = df_filtered.dropna(subset=["Hodnota"])

            try:
                df_filtered["Datetime"] = pd.to_datetime(
                    df_filtered["Datum"] + " " + df_filtered["Cas"], 
                    format="%Y-%m-%d %H:%M:%S", errors='coerce'
                )
                if df_filtered["Datetime"].isnull().any():
                      maska_nat = df_filtered["Datetime"].isnull()
                      df_filtered.loc[maska_nat, "Datetime"] = pd.to_datetime(
                        df_filtered.loc[maska_nat, "Datum"] + " " + df_filtered.loc[maska_nat, "Cas"],
                        format="%Y-%m-%d %H:%M", errors='coerce'
                      )
                df_filtered = df_filtered.sort_values(by="Datetime")
            except: pass
            
            df_final = df_filtered[["Datum", "Cas", "Model", "Linka", "Operator", "Smena", "Hodnota", "Limit_USL", "Limit_LSL", "Target", "Status"]].copy()
            return df_final
        except Exception as e:
            print(f"Chyba historie: {e}")
            return empty_df

    def ulozit_do_csv(self, datum, cas, hodnota, operator, smena, status):
        t= TEXTS[self.jazyk]
        file_exists = os.path.isfile(self.cesta_data)
        
        def to_excel(v): return str(v).replace(".", ",")

        try:
            with open(self.cesta_data, mode="a", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                if not file_exists:
                    writer.writerow(["Datum", "Cas", "Model", "Linka", "Operator", "Smena", "Hodnota", "Limit_USL", "Limit_LSL", "Target", "Status"])
                writer.writerow([
                    datum, cas, self.aktualni_model, self.current_set_line,
                    operator, smena, to_excel(hodnota),
                    to_excel(self.usl), to_excel(self.lsl), to_excel(self.target), status
                ])
                print(f"Uloženo do CSV.")
        except PermissionError:
            messagebox.showerror(t["error"], t["close_excel"], parent=self)
        except Exception as e:
            print(f"Chyba CSV: {e}")

    # --- UI METODY ---
    def umistit_okno_na_obrazovce(self, okno, sirka, vyska, typ_okna=""):
        sirka_obrazovky = okno.winfo_screenwidth()
        vyska_obrazovky = okno.winfo_screenheight()
        if typ_okna == "measurement_dialog":
            okno.resizable(False, False)
            x = int((sirka_obrazovky // 2) - (sirka // 2)+300)
            y = int((vyska_obrazovky // 2) - (vyska // 2))
            okno.geometry(f"{sirka}x{vyska}+{x}+{y}")
        else:
            x = int((sirka_obrazovky // 2) - (sirka // 2))
            y = int((vyska_obrazovky // 2) - (vyska // 2))
            okno.geometry(f"{sirka}x{vyska}+{x}+{y}")

    def change_language(self, choice):
        self.jazyk = choice
        self.settings.set("language", choice)
        self.clear_ui() 
        self.setup_ui() 
        if not self.df.empty:
            self.update_graph()

    def clear_ui(self):
        if hasattr(self, 'side_frame'): self.side_frame.destroy()
        if hasattr(self, 'top_frame'): self.top_frame.destroy()
        if hasattr(self, 'graph_frame'): self.graph_frame.destroy()
    
    def setup_ui(self):
        t = TEXTS[self.jazyk] 
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=0, minsize=300)
        self.grid_columnconfigure(1, weight=1)

        # BOČNÍ PANEL
        self.side_frame = ctk.CTkFrame(self, width=250, corner_radius=15, fg_color=("#F0F0F0", "#1a1a1a")) 
        self.side_frame.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(20, 10), pady=10)
        self.side_frame.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(self.side_frame, text=t["project_type"], font=("Arial", 20, "bold")).pack(pady=10, padx=10)
        self.lbl_model_display = ctk.CTkLabel(self.side_frame, text=self.aktualni_model, width=200, font=("Arial", 16))
        self.lbl_model_display.pack(pady=0, padx=10, fill="x")

        ctk.CTkLabel(self.side_frame, text=t["line"] +":", font=("Arial", 20, "bold")).pack(pady=10, padx=10)
        self.current_set_line = self.settings.get("line") # Refresh line
        ctk.CTkLabel(self.side_frame, text=self.current_set_line, font=("Arial", 18)).pack(pady=0, padx=10)
        
        text_smeny = t["current_shift"].format(shift_name=self.aktualni_smena)
        self.lbl_smena_info = ctk.CTkLabel(self.side_frame, text=text_smeny, font=("Arial", 16, "bold"))
        self.lbl_smena_info.pack(pady=5)

        ctk.CTkButton(self.side_frame, text=t["settings"], height=50, command=self.nastaveni_app, corner_radius=15, font=("Arial", 18, "bold")).pack(pady=10, padx=10, fill="x", side="bottom")
        
        self.lang_frame = ctk.CTkFrame(self.side_frame, fg_color="transparent")
        self.lang_frame.pack(side="bottom", pady=20, padx=10, fill="x")
        self.CTkLabel_model = ctk.CTkLabel(self.lang_frame, text=t["language"]+":", font=("Arial", 16))
        self.CTkLabel_model.pack(side="left", padx=5)
        self.lang_var = ctk.StringVar(value=self.jazyk)
        ctk.CTkOptionMenu(self.lang_frame, values=["CZ", "EN", "UA", "RO"], variable=self.lang_var,
                           command=self.change_language, width=150, height=50,corner_radius=15, font=("Arial", 18), dropdown_font=("Arial", 16)).pack(side="right", padx=15)
        
        self.btn_model = ctk.CTkButton(self.side_frame, text=t["add_new_model"], 
                                       command=self.pridat_nastaveni_modelu, 
                                       height=50, corner_radius=15, font=("Arial", 16, "bold"))
        self.btn_model.pack(pady=(20, 10), padx=10, fill="x", side="bottom")

        
        
        self.scroll_models = ctk.CTkScrollableFrame(self.side_frame, label_text="")
        self.scroll_models.pack(pady=5, padx=10, fill="both", expand=True)
        self.refresh_model_buttons()

        # --- HORNÍ PANEL ---
        self.top_frame = ctk.CTkFrame(self, height=150, fg_color=("#F0F0F0", "#1a1a1a"))
        self.top_frame.grid(row=0, column=1, sticky="ew", padx=(0, 20), pady=(10, 20))
        
        # Nastavení Gridu uvnitř top_frame (3 sloupce)
        # Sloupec 0 (vlevo) a 2 (vpravo) mají váhu 1 -> roztahují se a tlačí střed na střed
        # Sloupec 1 (střed) má váhu 0 -> drží si svou velikost
        self.top_frame.grid_columnconfigure(0, weight=1)
        self.top_frame.grid_columnconfigure(1, weight=0)
        self.top_frame.grid_columnconfigure(2, weight=1)
        self.top_frame.grid_rowconfigure(0, weight=1, minsize=150) # Vertikální centrování

        # --- 1. LEVÁ SEKCE (Tlačítka Analýza + Predikce) ---
        # Vytvoříme "pomocný frame", aby tlačítka držela u sebe a nerozjížděla se
        self.left_buttons_frame = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        self.left_buttons_frame.grid(row=0, column=0, sticky="w", padx=20) # sticky="w" = vlevo

        self.btn_data = ctk.CTkButton(
            self.left_buttons_frame, 
            text=t["data_and_histogram"], 
            command=self.otevrit_analyzu_dat, 
            height=60, width=190, 
            font=("Arial", 16, "bold"), corner_radius=15
        )
        self.btn_data.pack(side="left", padx=(5, 15)) # Pack je super pro věci vedle sebe

        self.btn_predikce = ctk.CTkButton(
            self.left_buttons_frame, 
            text=t["prediction"], 
            command=self.otevrit_predikci_dat, 
            height=60, width=190, 
            font=("Arial", 16, "bold"), corner_radius=15
        )
        self.btn_predikce.pack(side="left", padx=0) # Pack je super pro věci vedle sebe

        # --- 2. PROSTŘEDNÍ SEKCE (Nadpis + Časovač) ---
        self.middleframe = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        self.middleframe.grid(row=0, column=1) # Uprostřed (bez sticky)

        ctk.CTkLabel(self.middleframe, text=f"{t['big_title']}", font=("Arial", 26, "bold")).pack(side="top", padx=5, pady=5)
        
        self.timer_row = ctk.CTkFrame(self.middleframe, fg_color="transparent")
        self.timer_row.pack(side="top")
        
        ctk.CTkLabel(self.timer_row, text=t["remaining_time"]+":", font=("Arial", 18), text_color=("gray30", "gray70")).pack(side="left", padx=(10, 10))
        self.lbl_timer_val = ctk.CTkLabel(self.timer_row, text="--:--:--", font=("Arial", 32, "bold"), text_color=self.settings.get("color_theme"))
        self.lbl_timer_val.pack(side="left")

        # --- 3. PRAVÁ SEKCE (Stav procesu + Měření) ---
        # Vytvoříme kontejner, který zarovnáme doprava (sticky="e")
        # Uvnitř něj budou prvky vedle sebe (pack left)
        self.right_buttons_frame = ctk.CTkFrame(self.top_frame, fg_color="transparent")
        self.right_buttons_frame.grid(row=0, column=2, sticky="e", padx=(0, 20))

        # A) Text "Stav procesu"
        ctk.CTkLabel(self.right_buttons_frame, text=t["process_status_short"],
                     font=("Arial", 14, "bold"), text_color="gray60").pack(side="left", padx=(0, 5))

        # B) Barevná tečka (Kontrolka)
        # Použijeme Button, protože umí být perfektně kulatý (corner_radius = polovina width)
        # hover=False znamená, že na něj nejde klikat ani se nemění myší
        self.status_light = ctk.CTkButton(
            self.right_buttons_frame,
            text="", 
            width=24, height=24, 
            corner_radius=12, 
            fg_color="gray",  # Defaultní barva (než se načtou data)
            hover=False,
            state="disabled"  # Aby se nedalo kliknout
        )
        self.status_light.pack(side="left", padx=(0, 20))

        # C) Tlačítko Měření
        self.btn_measure = ctk.CTkButton(
            self.right_buttons_frame, 
            text=t["measure"], 
            command=self.open_input_dialog, 
            height=60, width=180, 
            font=("Arial", 16, "bold"), corner_radius=15
        )
        self.btn_measure.pack(side="left")


        # GRAF
        self.graph_frame = ctk.CTkFrame(self, fg_color=("#B9B9B9", "#2b2b2b"))                                
        self.graph_frame.grid(row=1, column=1, sticky="nsew", padx=0, pady=(0, 0))
        if self.aktualni_model == "N/A":
            self.zobrazit_prazdny_stav()
        else:
            self.init_graph()

    def update_process_status_light(self):
        """
        Vypočítá trend a změní barvu kontrolky v horním panelu.
        Zelená = Stabilní / Daleko od limitu
        Oranžová = Pozor (náraz < 500 měření)
        Červená = Kritické (náraz < 50 měření)
        """
        # Defaultní barva (když nejsou data)
        color = "gray"
        
        if self.df is not None and not self.df.empty and len(self.df) >= 10:
            import numpy as np
            
            # Bereme posledních 100 hodnot pro trend
            df_history = self.df.tail(100)
            y_values = df_history["Hodnota"].values
            x_values = np.arange(len(y_values))
            
            # Lineární regrese (y = ax + b)
            slope, intercept = np.polyfit(x_values, y_values, 1)
            
            # Logika barev (začínáme jako Zelená)
            color = "#00E676" # Zelená
            
            # Pokud je trend výrazný, počítáme náraz
            if abs(slope) > 0.0001: 
                aktualni_index = len(y_values)
                limit_k_kontrole = None
                
                # Jdeme nahoru -> kontrolujeme USL
                if slope > 0:
                    limit_k_kontrole = self.usl
                # Jdeme dolů -> kontrolujeme LSL
                else:
                    limit_k_kontrole = self.lsl
                
                # Výpočet, kdy narazíme: x = (Limit - b) / a
                cilovy_x = (limit_k_kontrole - intercept) / slope
                zbyva = cilovy_x - aktualni_index
                
                # Vyhodnocení vzdálenosti
                if zbyva < 50:
                    color = "#FF1744" # Červená (Kritické)
                elif zbyva < 500: # Tento limit si uprav podle citu (třeba 200)
                    color = "#FF9100" # Oranžová (Varování)
        
        # Nastavení barvy kontrolky
        try:
            self.status_light.configure(fg_color=color)
        except:
            pass

    def otevrit_analyzu_dat(self):
        t = TEXTS[self.jazyk]
        
        if self.aktualni_model == "N/A":
             messagebox.showinfo(t["alert_error"], t["choose_model_first"])
             return
             
        if self.df.empty:
            messagebox.showinfo(t["alert_error"], t["no_data_for_model"])
            return

        # Otevřeme naše nové okno a předáme mu "self" (rodiče)
        # Díky tomu si okno samo sáhne pro df, usl, lsl atd.
        DataAnalysisDialog(self)

    def otevrit_predikci_dat(self):
        t = TEXTS[self.jazyk]
        if self.aktualni_model == "N/A":
             messagebox.showinfo(t["alert_error"], t["choose_model_first"])
             return
        if self.df.empty:
                messagebox.showinfo(t["alert_error"], t["no_data_for_model"])
                return
        df_history = self.df.tail(150).copy()
        if len(df_history) < pocet_pro_ucl_lcl_fix_v_pripade_vypocitanych_control_limitu: # dokud nemám LCL a UCL fixní, potřebuji víc dat pro spolehlivou predikci
            messagebox.showinfo(t["prediction"], t["not_enough_data_pred"].format(minimum=pocet_pro_ucl_lcl_fix_v_pripade_vypocitanych_control_limitu))
            return
        # Otevřeme naše nové okno a předáme mu "self" (rodiče)
        # Díky tomu si okno samo sáhne pro df, usl, lsl atd.
        PredictionDialog(self)

    def refresh_model_buttons(self):
        """
        Načte modely z CSV, vyfiltruje ty, které patří k aktuální lince,
        a vytvoří pro ně tlačítka ve scrollable frame.
        """
        # 1. Vyčistit stará tlačítka
        for widget in self.scroll_models.winfo_children():
            widget.destroy()

        # 2. Najít modely pro tuto linku
        found_models = []
        try:
            with open(self.cesta_modely, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f, delimiter=';')
                for row in reader:
                    # Filtrujeme pouze modely pro aktuální linku (např. L64)
                    if row["Linka"] == self.current_set_line:
                        found_models.append(row["Model"])
        except Exception as e:
            print(f"Chyba při načítání tlačítek: {e}")

        # 3. Vytvořit tlačítka
        # Seřadíme je abecedně
        for model_name in sorted(found_models):
            # Barva tlačítka: Pokud je model aktivní, bude modré, jinak tmavě šedé
            is_active = (model_name == self.aktualni_model)
            fg_color = self.settings.get("color_theme") if is_active else "transparent"
            border_width = 2 if is_active else 1
            border_color = self.settings.get("color_theme") if is_active else "gray40"
            
            btn = ctk.CTkButton(
                self.scroll_models, 
                text=model_name, 
                height=50,
                fg_color=fg_color,
                border_width=border_width,
                border_color=border_color,
                text_color=("black", "white") if not is_active else "white",
                anchor="w", # Text zarovnaný doleva
                font=("Arial", 16),
                # Použijeme lambda s defaultním argumentem pro zachycení hodnoty v cyklu
                command=lambda m=model_name: self.kliknuti_na_model_v_seznamu(m)
            )
            btn.pack(fill="x", pady=5, padx=5)
            btn.bind("<Button-3>", lambda event, m=model_name: self.zobrazit_context_menu(event, m))
    
    def zobrazit_context_menu(self, event, model_name):
        """Vytvoří a zobrazí vyskakovací menu u kurzoru myši."""
        t= TEXTS[self.jazyk]
        options = [
            {
                "text": t["edit_model"], 
                "command": lambda: self.upravit_model_z_menu(model_name)
            },
            {
                "separator": True # Čára
            },
            {
                "text": t["delete_model"], 
                "command": lambda: self.smazat_model_z_menu(model_name),
                "text_color": "#ff5555",      # Červený text pro mazání
                "hover_color": "#5c2b2b"      # Červené podbarvení při najetí
            }
        ]
        ModernMenu(self, event.x_root, event.y_root, options)

    def overit_heslo(self, okno=None):
        """
        Univerzální metoda. Otevře PasswordDialog a vrátí True/False.
        """
        aktualni_jazyk = getattr(self, "jazyk", "CZ") 
        t = TEXTS.get(aktualni_jazyk, TEXTS["CZ"])
        # 1. Vytvoříme instanci dialogu
        rodic = okno if okno else self
        dialog = PasswordDialog(rodic, jazyk=aktualni_jazyk)
        
        # 2. Vytáhneme z něj, co uživatel zadal (díky wait_window to počká)
        zadane = dialog.get_input()
        
        # 3. Pokud uživatel zavřel okno křížkem (zadane je None) -> NEPUSTIT
        if zadane is None:
            return False
            
        # 4. Kontrola hesla
        if zadane == heslo_kamkoliv:  # ZDE JE VAŠE HESLO
            return True
        else:
            messagebox.showerror(t["alert_error"], t["incorrect_password"], parent=rodic)
            return False
        
    def upravit_model_z_menu(self, model_name):
        """Jen pomocná metoda pro spuštění dialogu."""
        if not self.overit_heslo():
            return
        ModelSetupDialog(self, edit_model=model_name)

    def smazat_model_z_menu(self, model_name):
        """Logika pro smazání modelu."""
        if not self.overit_heslo():
            return
        self.aktualni_model = "N/A"
        # ... další kód ...
        # 2. POTVRZENÍ
        t = TEXTS[self.jazyk]
        odpoved = messagebox.askyesno(
            t["delete_model"], 
            t["warning_delete_model"].format(model=model_name)
        )
        if not odpoved:
            return
        self.stop_timer()
        # 3. MAZÁNÍ Z CSV
        temp_rows = []
        try:
            with open(self.cesta_modely, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f, delimiter=';')
                fieldnames = reader.fieldnames
                for row in reader:
                    # Pokud to NENÍ ten model na té lince, tak ho zachováme
                    # (Smažeme jen ten, kde se shodu Model i Linka)
                    if not (row["Model"] == model_name and row["Linka"] == self.current_set_line):
                        temp_rows.append(row)
            
            # Zápis zpět
            with open(self.cesta_modely, mode="w", encoding="utf-8-sig", newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
                writer.writeheader()
                writer.writerows(temp_rows)
                
            print(f"Model {model_name} byl smazán.")
            self.zobrazit_prazdny_stav()
        except Exception as e:
            messagebox.showerror("Chyba", f"Nepodařilo se smazat model:\n{e}", parent=self)
            return

        # 4. AKTUALIZACE APLIKACE
        # Pokud jsme smazali model, který je zrovna aktivní -> musíme resetovat na Empty State
        if self.aktualni_model == model_name:
            self.aktualni_model = "N/A"
            self.settings.set("project", "N/A")
            self.zobrazit_prazdny_stav()
            self.lbl_model_display.configure(text="N/A")

        # 5. REFRESH TLAČÍTEK (Tlačítko zmizí)
        self.refresh_model_buttons()

    def _nacist_data_z_csv(self, model_name):
        """Načte data modelu z CSV. Tato funkce musí být v hlavní aplikaci."""
        try:
            # Tady už používáme jen self, protože jsme v hlavní třídě
            with open(self.cesta_modely, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f, delimiter=';')
                for row in reader:
                    # Hledáme model a linku
                    if row["Model"] == model_name and row["Linka"] == self.current_set_line:
                        return {
                            "USL": float(row["USL"].replace(",", ".")),
                            "LSL": float(row["LSL"].replace(",", ".")),
                            "Target": float(row["Target"].replace(",", ".")),
                            # Bezpečné načtení Timeru
                            "Timer": int(row.get("Timer", "240")),
                            "UCL": row.get("UCL", "").replace(",", "."),
                            "LCL": row.get("LCL", "").replace(",", ".")
                        }
        except Exception as e:
            print(f"Chyba při čtení CSV v SPCApp: {e}")
        return None

    def otevrit_upravu_modelu(self, event, model_name):
        """
        Otevře dialog nastavení, ale řekne mu, že má načíst data 
        pro konkrétní 'model_name' z CSV.
        """
        print(f"Pravý klik na: {model_name} -> Otevírám úpravu.")
        ModelSetupDialog(self, edit_model=model_name)

    def kliknuti_na_model_v_seznamu(self, model_name):
        """Co se stane, když kliknu na tlačítko modelu v seznamu."""
        t= TEXTS[self.jazyk]

        opravdu_prepnout= messagebox.askyesno(
            t["really_switch_model"], 
            t["confirm_switch_model"].format(model_name=model_name))

        if not opravdu_prepnout:
            return

        #if model_name == self.aktualni_model:
        #    return # když kliknu na stejný model, dám nový reset timer na rozjezd čas
            
        # 1. Přepnout logiku
        self.zmena_modelu(model_name)
        
        # 2. Aktualizovat UI (zvýraznění tlačítek)
        self.refresh_model_buttons()
        self.lbl_model_display.configure(text=model_name)
        self.reset_timer(typ="rozjezd")

        self.aktualni_smena = "N/A"
        text_smeny = t["current_shift"].format(shift_name=self.aktualni_smena)
        self.lbl_smena_info.configure(text=text_smeny)
        
        if self.aktualni_model == "N/A":
            self.zobrazit_prazdny_stav()

        # 3. Pokud byl prázdný stav (šipka), zrušit ho
        if not hasattr(self, 'ax') or self.ax is None:
             self.init_graph()
        else:
             self.update_graph()

    def zobrazit_prazdny_stav(self):
        for widget in self.graph_frame.winfo_children():
            widget.destroy()
        self.ax = None
        self.fig = None
        self.canvas = None
        self.toolbar_logic = None    
        self.graph_frame.grid_columnconfigure(0, weight=1)
        self.graph_frame.grid_rowconfigure(0, weight=1)

        msg_frame = ctk.CTkFrame(self.graph_frame, fg_color="transparent")
        msg_frame.grid(row=0, column=0)
        
        ctk.CTkLabel(msg_frame, text="⇐", font=("Arial", 80, "bold"), text_color="orange").pack(side="left", padx=20)
        
        t = TEXTS[self.jazyk]
        text_vyzvy = t["no_model_selected"]
        ctk.CTkLabel(msg_frame, text=text_vyzvy, font=("Arial", 24, "bold"), justify="left").pack(side="left")

    def pridat_nastaveni_modelu(self):
        #přidat heslo dialog
        if not self.overit_heslo():
            return
        ModelSetupDialog(self)

    def get_graph_colors(self):
        mode = ctk.get_appearance_mode()
        return ("#e5e5e5", "#ffffff", "black") if mode == "Light" else ("#2b2b2b", "#333333", "white")
    
    def init_graph(self):
        # 1. Vyčistíme staré widgety
        for widget in self.graph_frame.winfo_children():
            widget.destroy()

        bg_color, face_color, text_color = self.get_graph_colors()

        # 2. Nastavíme GRID layout pro graph_frame
        # Řádek 0 = Graf (roztahuje se)
        # Řádek 1 = Lišta s tlačítky (fixní výška)
        self.graph_frame.grid_rowconfigure(0, weight=1) 
        self.graph_frame.grid_rowconfigure(1, weight=0)
        self.graph_frame.grid_columnconfigure(0, weight=1)

        # 3. Matplotlib Figure
        self.fig = Figure(figsize=(10, 6), dpi=100) 
        self.fig.patch.set_facecolor(bg_color)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor(face_color)
        
        # 4. Canvas (Graf) - Používáme GRID
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.graph_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 0))

        # 5. --- OPRAVA CHYBY S PACK/GRID ---
        dummy_frame = ctk.CTkFrame(self.graph_frame, width=0, height=0)
        dummy_frame.grid(row=2, column=0) # Dáme ho někam bokem
        dummy_frame.grid_remove()         # A hned ho schováme, aby nebyl vidět

        
        # Logiku pošleme do dummy_frame, ne přímo do graph_frame!
        self.toolbar_logic = NavigationToolbar2Tk(self.canvas, dummy_frame)
        self.toolbar_logic.update()
        # -----------------------------------
        
        # 6. Vytvoření našich vlastních tlačítek
        self.create_custom_toolbar()
        self.canvas.mpl_connect("motion_notify_event", self.on_hover)

        self.after(300, self.update_graph)

    def create_custom_toolbar(self):
        """Vytvoří lištu s tlačítky v dolní části rámečku pomocí Gridu."""
        
        # Rámeček pro tlačítka dáme do řádku 1 (pod graf)
        toolbar_frame = ctk.CTkFrame(self.graph_frame, fg_color="transparent", height=40)
        toolbar_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        t= TEXTS[self.jazyk]
        
        def load_icon(name_black, name_white):
            try:
                # Použijeme resource_path pro kompatibilitu s .exe
                path_black = self.resource_path(f"icons/{name_black}")
                path_white = self.resource_path(f"icons/{name_white}")
                
                return ctk.CTkImage(
                    light_image=Image.open(path_black),
                    dark_image=Image.open(path_white),
                    size=(20, 20) # Velikost ikony
                )
            except Exception as e:
                print(f"Varování: Ikona {name_black} nebyla nalezena. ({e})")
                return None
            
        icon_home = load_icon("home_black.png", "home_white.png")
        icon_pan  = load_icon("hand_black.png", "hand_white.png")
        icon_zoom = load_icon("zoom_black.png", "zoom_white.png")
        icon_save = load_icon("save_black.png", "save_white.png")

        # Styl tlačítek
        btn_params = {
            "width": 120, 
            "height": 50, 
            "corner_radius": 8, 
            "font": ("Arial", 12, "bold"),
            "fg_color": ("#ddd", "#3a3a3a"), # Šedá barva pozadí
            "text_color": ("black", "white"),
            "compound": "left", # Ikona vlevo, text vpravo
            "anchor": "center"
        }

        btn_home = ctk.CTkButton(
            toolbar_frame, 
            text=t["reset_view"], 
            image=icon_home, 
            command=self.reset_view,
            **btn_params
        )
        btn_home.pack(side="left", padx=5)
        
        # PAN (Posun)
        self.btn_pan = ctk.CTkButton(
            toolbar_frame, 
            text=t["pan"], 
            image=icon_pan, 
            command=self.toggle_pan, 
            **btn_params
        )
        self.btn_pan.pack(side="left", padx=5)
        
        # ZOOM (Lupa)
        self.btn_zoom = ctk.CTkButton(
            toolbar_frame, 
            text=t["zoom"], 
            image=icon_zoom, 
            command=self.toggle_zoom, 
            **btn_params
        )
        self.btn_zoom.pack(side="left", padx=5)
        
        # SAVE (Uložit)
        btn_save = ctk.CTkButton(
            toolbar_frame, 
            text=t["save"], 
            image=icon_save, 
            command=self.ulozit_do_pdf, 
            **btn_params
        )
        btn_save.pack(side="right", padx=5)

    def resource_path(self, relative_path):
        """ Získá absolutní cestu k souboru, funguje pro dev i pro PyInstaller exe """
        try:
            # PyInstaller vytvoří dočasnou složku _MEIPASS
            base_path = sys._MEIPASS
        except Exception:
            # Tady je změna: použijeme cestu ke skriptu, ne k pracovní složce
            base_path = os.path.dirname(os.path.abspath(__file__))

        return os.path.join(base_path, relative_path)
    
    def toggle_pan(self):
        self.toolbar_logic.pan() # Zavolá funkci matplotlibu
        # Změna barvy tlačítka podle stavu
        if self.toolbar_logic.mode == "pan/zoom": # Matplotlib interní název pro Pan mode
             self.btn_pan.configure(fg_color="#3B8ED0", text_color="white") # Aktivní (Modrá)
             self.btn_zoom.configure(fg_color=("#ddd", "#3a3a3a"), text_color=("black", "white")) # Reset Zoomu
        else:
             self.btn_pan.configure(fg_color=("#ddd", "#3a3a3a"), text_color=("black", "white")) # Deaktivní

    def toggle_zoom(self):
        self.toolbar_logic.zoom() # Zavolá funkci matplotlibu
        if self.toolbar_logic.mode == "zoom rect": # Matplotlib interní název pro Zoom mode
             self.btn_zoom.configure(fg_color="#3B8ED0", text_color="white") # Aktivní (Modrá)
             self.btn_pan.configure(fg_color=("#ddd", "#3a3a3a"), text_color=("black", "white")) # Reset Pan
        else:
             self.btn_zoom.configure(fg_color=("#ddd", "#3a3a3a"), text_color=("black", "white")) # Deaktivní
    
    def update_graph(self):
        if not hasattr(self, 'ax') or self.ax is None:
            return
        
        # 1. Styling a vyčištění
        bg_color, face_color, text_color = self.get_graph_colors()
        self.ax.clear()
        self.fig.patch.set_facecolor(bg_color)
        self.ax.set_facecolor(face_color)
        
        self.ax.tick_params(colors=text_color)
        self.ax.xaxis.label.set_color(text_color)
        self.ax.yaxis.label.set_color(text_color)
        for spine in self.ax.spines.values(): spine.set_edgecolor(text_color)
        self.ax.grid(True, color=text_color, alpha=0.15)

        titulek_text = TEXTS[self.jazyk]["spc_trend"]
        MIN_BODU_SPC = minimalni_pocet_namerench_bodu_spc

        if self.df.empty:
            self.ax.set_title(titulek_text, color=text_color)
            self.canvas.draw()
            return

        self.df_plot = self.df.copy()

        # --- ČIŠTĚNÍ DAT ---
        # 1. Hodnoty na čísla (aby graf nepadal)
        self.df_plot["Hodnota"] = self.df_plot["Hodnota"].astype(str).str.replace(',', '.')
        self.df_plot["Hodnota"] = pd.to_numeric(self.df_plot["Hodnota"], errors='coerce')
        
        # 2. Vyhodíme řádky, kde chybí hodnota
        self.df_plot = self.df_plot.dropna(subset=["Hodnota"])
        
        if self.df_plot.empty: return

        aktualni_pocet = len(self.df_plot)

        # --- PŘÍPRAVA POPISKŮ (Datum 24.2. + Čas) ---

        # Funkce pro formátování data (řeší tvůj požadavek i chybu float)
        def formatuj_datum(text):
            # BEZPEČNÝ PŘEVOD: I když je tam float(nan), udělá z toho string "nan"
            t = str(text).strip()
            
            # Pokud je to prázdné nebo "nan", vrátíme otazník
            if t.lower() == 'nan' or not t:
                return "?"
            
            try:
                # Pokud je formát YYYY-MM-DD (obsahuje pomlčky)
                if "-" in t:
                    casti = t.split("-")
                    # Očekáváme [Rok, Měsíc, Den]
                    if len(casti) == 3:
                        den = int(casti[2])   # int() odstraní nulu (05 -> 5)
                        mesic = int(casti[1]) # int() odstraní nulu (02 -> 2)
                        return f"{den}.{mesic}." # Výsledek: "24.2."
            except:
                pass
            
            # Pokud se to nepovede (jiný formát), vrátíme původní text
            return t

        # Funkce pro formátování času (HH:MM)
        def formatuj_cas(text):
            t = str(text).strip()
            if len(t) >= 5:
                return t[:5] 
            return t

        # Aplikujeme funkce na sloupce
        datumy = self.df_plot["Datum"].apply(formatuj_datum)
        casy = self.df_plot["Cas"].apply(formatuj_cas)

        # Spojíme do finálního popisku
        self.df_plot["Label"] = datumy+ " "+ casy
        
        # Uložíme seznam popisků pro osu X (použije ho FuncFormatter níže)
        vsechny_popisky = self.df_plot["Label"].tolist()
        
        # Vytvoříme číselný index pro osu X (aby se čáry spojily)
        self.df_plot["Idx"] = range(aktualni_pocet)

        # 4. Statistiky (UCL/LCL)
        mean = self.df_plot["Hodnota"].mean()
        ucl_final = None
        lcl_final = None
        is_fixed = False
        label_spc = "UCL/LCL"

        if hasattr(self, 'fixed_ucl') and self.fixed_ucl is not None:
            ucl_final = self.fixed_ucl
            lcl_final = self.fixed_lcl
            is_fixed = True
            label_spc = "UCL/LCL (Fix)"
        elif aktualni_pocet >= MIN_BODU_SPC:
             std = self.df_plot["Hodnota"].std()
             if std > 0:
                ucl_final = mean + 3*std
                lcl_final = mean - 3*std
                label_spc = "UCL/LCL (Auto)"
        
        if aktualni_pocet < MIN_BODU_SPC and not is_fixed:
             titulek_text += f" {TEXTS[self.jazyk]['calibration']}: ({aktualni_pocet}/{MIN_BODU_SPC})"

        # 5. VYKRESLENÍ GRAFU
        # DŮLEŽITÉ: x="Idx" (čísla) zajistí, že čára vede skrz body správně
        sns.lineplot(data=self.df_plot, x="Idx", y="Hodnota", ax=self.ax, color="#3B8ED0", marker='o', zorder=3)
        sns.scatterplot(data=self.df_plot, x="Idx", y="Hodnota", ax=self.ax, hue="Status", 
                        palette={"OK": "#00E676", "NOK": "#FF1744"}, s=100, zorder=5, legend=True)
        if self.ax.collections:
            self.sc_collection = self.ax.collections[-1]
        else:
            self.sc_collection = None
        
        self.annot = self.ax.annotate(
            "", 
            xy=(0,0), 
            xytext=(15, 15),
            textcoords="offset points",
            # boxstyle="round,pad=0.5" udělá hezké oblé rohy a polstrování
            bbox=dict(boxstyle="round,pad=0.5", fc="white", ec="black", alpha=0.9),
            arrowprops=dict(arrowstyle="->", color="black"),
            fontsize=10 # Velikost písma v bublině
        )
        self.annot.set_visible(False)

        # --- DYNAMICKÉ OSY (ZOOM) ---
        # Funkce, která převede číslo na ose X (Idx) zpět na text (Label)
        def format_fn(value, tick_number):
            idx = int(value)
            if 0 <= idx < len(vsechny_popisky):
                return vsechny_popisky[idx]
            return ""

        from matplotlib.ticker import MaxNLocator, FuncFormatter
        # MaxNLocator zajistí, že se popisky nebudou překrývat (max 25 na obrazovku)
        locator = MaxNLocator(nbins=25, integer=True) 
        self.ax.xaxis.set_major_locator(locator)
        self.ax.xaxis.set_major_formatter(FuncFormatter(format_fn))

        # Otočení popisků pro lepší čitelnost
        self.ax.tick_params(axis='x', rotation=45, labelsize=8)
        
        # Popisky os a titulek
        txt_cas = TEXTS[self.jazyk].get("graph_time", "Time")
        txt_hodnota = TEXTS[self.jazyk].get("lbl_value", "Value")
        self.ax.set_xlabel(txt_cas, color=text_color, fontsize=12)
        self.ax.set_ylabel(txt_hodnota, color=text_color, fontsize=12)
        self.ax.set_title(titulek_text, color=text_color)

        # 6. Limity (čáry)
        self.ax.axhline(self.usl, color='#ff5555', linestyle='--', label="USL/LSL")
        self.ax.axhline(self.lsl, color='#ff5555', linestyle='--')
        self.ax.axhline(self.target, color="#001EC5", linestyle='-', alpha=0.3, label="Target", linewidth=3)
        
        if mean is not None:
            self.ax.axhline(mean, color='black', linestyle=':', alpha=0.6, label="Mean")
        
        if ucl_final is not None:
            style = '-' if is_fixed else '-.'
            self.ax.axhline(ucl_final, color='orange', linestyle=style, alpha=0.8, label=label_spc)
            self.ax.axhline(lcl_final, color='orange', linestyle=style, alpha=0.8)

        # 7. Zoom osy Y (aby graf nebyl nalepený na okrajích)
        vals = [self.usl, self.lsl] + self.df_plot["Hodnota"].tolist()
        if ucl_final: vals.extend([ucl_final, lcl_final])
        
        vals = [v for v in vals if pd.notnull(v)]
        if vals:
            mn, mx = min(vals), max(vals)
            rng = (mx - mn) if mx != mn else 1.0
            self.ax.set_ylim(mn - rng*0.15, mx + rng*0.15)
        
        # Legenda
        self.ax.legend(loc='upper right', bbox_to_anchor=(1, 1), facecolor=bg_color, labelcolor=text_color, fontsize='small')
        
        self.fig.tight_layout()
        self.canvas.draw()

    def on_hover(self, event):
        # 1. Základní kontroly (zda jsme v grafu a máme data)
        if event.inaxes != self.ax: return
        if not hasattr(self, 'sc_collection') or self.sc_collection is None: return
        if not hasattr(self, 'annot'): return

        # 2. Detekce bodu pod myší
        cont, ind = self.sc_collection.contains(event)
        
        if cont:
            try:
                # Získáme data o bodu
                idx_v_kolekci = ind["ind"][0]
                radek = self.df_plot.iloc[idx_v_kolekci]
                
                # Načtení hodnot
                datum_str = radek.get("Label", "?")
                hodnota = radek["Hodnota"]
                oper = radek["Operator"]
                status = radek["Status"]
                
                # Text bubliny
                text_bubliny = f"Čas: {datum_str}\nHodnota: {hodnota}\nOp: {oper}\nStatus: {status}"
                
                # --- NASTAVENÍ BAREV (Dark vs Light) ---
                is_dark = ctk.get_appearance_mode() == "Dark"
                
                # A) Pokud je to ZMETEK (NOK) -> Vždy červená
                if status == "NOK":
                    bg_color = "#D32F2F"  # Tmavší červená (lépe čitelná)
                    text_color = "white"
                    border_color = "#FFCDD2" # Světle růžový okraj
                    arrow_color = "#D32F2F"
                    
                # B) Pokud je to OK a máme TMAVÝ REŽIM
                elif is_dark:
                    bg_color = "#2B2B2B"  # Tmavě šedá (ladí k aplikaci)
                    text_color = "#FFFFFF" # Bílé písmo
                    border_color = "#555555" # Šedý rámeček
                    arrow_color = "#FFFFFF"

                # C) Pokud je to OK a máme SVĚTLÝ REŽIM
                else:
                    bg_color = "#F0F0F0"  # Velmi světle šedá (ne čistě bílá)
                    text_color = "#000000" # Černé písmo
                    border_color = "#333333" # Tmavý rámeček
                    arrow_color = "#333333"

                # --- APLIKACE BAREV NA BUBLINU ---
                self.annot.xy = (event.xdata, event.ydata)
                self.annot.set_text(text_bubliny)
                
                # 1. Barva textu
                self.annot.set_color(text_color)
                
                # 2. Barva pozadí a rámečku bubliny
                self.annot.get_bbox_patch().set_facecolor(bg_color)
                self.annot.get_bbox_patch().set_edgecolor(border_color)
                self.annot.get_bbox_patch().set_alpha(0.95) # Skoro neprůhledné
                
                # 3. Barva šipky (musíme změnit vlastnosti arrow_patch)
                if self.annot.arrow_patch:
                    self.annot.arrow_patch.set_color(arrow_color)

                self.annot.set_visible(True)
                self.canvas.draw_idle()
                
            except Exception as e:
                print(f"Chyba hover: {e}")
        else:
            # Myš odjela pryč -> schovat
            if self.annot.get_visible():
                self.annot.set_visible(False)
                self.canvas.draw_idle()

    def ulozit_do_pdf(self):
        """Vlastní funkce pro uložení grafu přímo do PDF"""
        try:
            # 1. Zeptáme se uživatele, kam to chce (přednastavíme .pdf)
            cesta = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF dokument", "*.pdf"), ("Obrázek PNG", "*.png")],
                title="Uložit graf"
            )
            
            # 2. Pokud uživatel nevybral 'Storno'
            if cesta:
                # self.canvas.figure je ten objekt s grafem, co máš v okně
                self.canvas.figure.savefig(cesta, bbox_inches='tight', dpi=300)
                messagebox.showinfo("Hotovo", f"Graf byl uložen jako PDF do:\n{cesta}")
        
        except Exception as e:
            messagebox.showerror("Chyba", f"Nepodařilo se uložit PDF:\n{e}")

    def zmena_modelu(self, model):
        print(f"Měním model na: {model}")
        self.aktualni_model = model
        self.settings.set("project", model)
        self.fixed_ucl = None
        self.fixed_lcl = None
        
        
        nasel_v_db = False
        try:
            with open(self.cesta_modely, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f, delimiter=';')
                for row in reader:
                    # Hledáme shodu Modelu i Linky
                    if row["Model"] == model and row["Linka"] == self.current_set_line:
                        self.usl = float(row["USL"].replace(",", "."))
                        self.lsl = float(row["LSL"].replace(",", "."))
                        self.target = float(row["Target"].replace(",", "."))
                        loaded_timer = int(row.get("Timer", "240"))
                        self.shift_duration = loaded_timer * 60
                        self.timer_seconds = self.shift_duration
                        raw_ucl = row.get("UCL", "")
                        raw_lcl = row.get("LCL", "")
                        if raw_ucl and raw_ucl.strip():
                            self.fixed_ucl = float(raw_ucl.replace(",", "."))
                        
                        if raw_lcl and raw_lcl.strip():
                            self.fixed_lcl = float(raw_lcl.replace(",", "."))
                        nasel_v_db = True
                        
                        print(f"Limity načteny z DB: {self.usl} / {self.target} / {self.lsl}")
                        break
        except Exception as e:
            print(f"Chyba při čtení definice modelu: {e}")

        # ---------------------------------------------------------
        # KROK 2: Pokud není v DB, zkusíme historii nebo default (Fallback)
        # ---------------------------------------------------------
        self.df = self.nacteni_starych_dat_z_csv()

        if not nasel_v_db:
            print("Model není v DB, zkouším historii...")
            limity_z_historie = False
            if not self.df.empty:
                try:
                    posledni = self.df.iloc[-1]
                    if "Limit_USL" in posledni and "Limit_LSL" in posledni and "Target" in posledni:
                        def parse_val(v): return float(str(v).replace(",", "."))
                        self.usl = parse_val(posledni["Limit_USL"])
                        self.lsl = parse_val(posledni["Limit_LSL"])
                        self.target = parse_val(posledni["Target"])
                        limity_z_historie = True
                except: pass
            
            if not limity_z_historie:
                # Úplný default, pokud nevíme nic
                self.usl = 5.0
                self.lsl = 3.0
                self.target = 4.0

        # ---------------------------------------------------------
        # KROK 3: Uložení aktuálně platných hodnot do nastavení (JSON)
        # ---------------------------------------------------------
        # Aby si aplikace pamatovala stav i po pádu
        self.settings.set("usl", self.usl)
        self.settings.set("lsl", self.lsl)
        self.settings.set("target", self.target)
        
        print(f"Model změněn na {model}, načteno {len(self.df)} záznamů.")
        # ---------------------------------------------------------
        # KROK 4: Překreslení grafu
        # ---------------------------------------------------------
        self.update_graph()
        self.aktualizovat_semafor()
        
    def stop_timer(self):
        """Zastaví časovač, pokud běží."""
        if self.timer_running is not None:
            try:
                self.after_cancel(self.timer_running) # ZRUŠÍ naplánovaný update
            except:
                pass
            self.timer_running = None
        
        # Volitelné: Vynulovat label nebo ukázat pomlčky
        try:
            self.lbl_timer_val.configure(text="--:--:--", text_color=self.settings.get("color_theme"))
        except:
            pass

    def reset_timer(self, typ="standard"):
        """
        typ="rozjezd" -> Nastaví natvrdo 10 minut (při změně modelu).
        typ="standard" -> Načte interval z CSV (při uložení kusu).
        """
        # 1. Zastavíme starý časovač
        self.stop_timer()

        if self.aktualni_model == "N/A" or not self.aktualni_model:
            try:
                self.lbl_timer_val.configure(text="--:--:--", text_color="gray")
            except: pass
            return

        minuty = 0

        # 2. Rozhodování podle typu situace
        if typ == "rozjezd":
            # Situace: Změna modelu -> Vždy 10 minut
            minuty = pocet_minut_na_rozjezd
            
        else: # typ == "standard"
            # Situace: Po změření -> Načíst interval z modely_spc.csv
            
            # --- OPRAVA ZDE: Používáme self, ne self.parent ---
            data_modelu = self._nacist_data_z_csv(self.aktualni_model)
            # --------------------------------------------------

            if data_modelu and "Timer" in data_modelu:
                minuty = data_modelu["Timer"]
            else:
                print("Nepodařilo se načíst Timer z CSV, dávám default 60.")
                minuty = 60 # Záchranná hodnota

        # 3. Nastavení a start
        self.timer_seconds = minuty * 60
        
        # Reset barvy na normální
        try:
            self.lbl_timer_val.configure(text_color=self.settings.get("color_theme", "text_color") if isinstance(self.settings.get("color_theme"), str) else "white")
        except:
            pass

        self.update_timer()

    def reset_view(self):
        """Resetuje pohled na výchozí stav (vypne zoom/pan a překreslí)."""
        # 1. Pokud je zapnutý nějaký nástroj (Lupa/Ruka), vypneme ho
        if self.toolbar_logic.mode != "":
            # Matplotlib nemá přímou funkci "turn off", ale můžeme zavolat tu aktivní znovu, což ji vypne
            if self.toolbar_logic.mode == "pan/zoom":
                self.toggle_pan()
            elif self.toolbar_logic.mode == "zoom rect":
                self.toggle_zoom()
        
        # 2. Resetujeme vizuální styl tlačítek (pro jistotu)
        try:
            self.btn_pan.configure(fg_color=("#ddd", "#3a3a3a"), text_color=("black", "white"))
            self.btn_zoom.configure(fg_color=("#ddd", "#3a3a3a"), text_color=("black", "white"))
        except:
            pass

        # 3. To nejdůležitější: Znovu vykreslíme graf, což ho automaticky vycentruje
        self.update_graph()

    def update_timer(self):
        """Samotná smyčka odpočtu."""
        m, s = divmod(self.timer_seconds, 60)
        h, m = divmod(m, 60)
        
        try:
            self.lbl_timer_val.configure(text=f"{h:02d}:{m:02d}:{s:02d}")
        except:
            return # Pokud label neexistuje (aplikace se zavírá), skončíme

        if self.timer_seconds > 0:
            self.timer_seconds -= 1
            # Uložíme si ID tohoto volání, abychom ho mohli později zrušit
            self.timer_running = self.after(1000, self.update_timer)
        else:
            self.timer_running = None
            try:
                self.lbl_timer_val.configure(text_color="red")
            except:
                pass
            
            # Čas vypršel -> Akce
            self.open_input_dialog(zpusob_otevreni="timer_expired")

    def open_input_dialog(self, zpusob_otevreni=None):
        t= TEXTS[self.jazyk]
        if self.aktualni_model == "N/A" or not self.aktualni_model:
            messagebox.showwarning(t["warning"], t["no_model_selected"])
            return
        if not hasattr(self, 'toplevel_window') or self.toplevel_window is None or not self.toplevel_window.winfo_exists():
            self.toplevel_window = InputDialog(self, zpusob_otevreni=zpusob_otevreni)
        else:
            self.toplevel_window.focus()

    def add_record(self, value, operator, smena):
        t = TEXTS[self.jazyk]
        je_NOK = False
        spc_varovani = False
        msg = ""
        value = round(float(value), 3)
        if value > self.usl:
            msg = f"{t['value_high']}\n\n{t['measured']}: {value}\n{t['limit_usl']}: {self.usl}"
            je_NOK = True
        elif value < self.lsl:
            msg = f"{t['value_low']}\n\n{t['measured']}: {value}\n{t['limit_lsl']}: {self.lsl}"
            je_NOK = True

        if not je_NOK and self.fixed_ucl is not None and self.fixed_lcl is not None:
            msg1ab = t['spc_above'].format(value=value, limit=self.fixed_ucl)
            msg1bl = t['spc_below'].format(value=value, limit=self.fixed_lcl)
            if value > self.fixed_ucl:
                msg = f"{msg1ab}\n\n{t['measured']}: {value}\nUCL: {self.fixed_ucl}"
                spc_varovani = True
            elif value < self.fixed_lcl:
                msg = f"{msg1bl}\n\n{t['measured']}: {value}\nLCL: {self.fixed_lcl}"
                spc_varovani = True

        if je_NOK:
            # Pípnutí (volitelné)
            try: self.bell() 
            except: pass
            
            # Vyskočí varovné okno
            self.after(300, lambda: messagebox.showwarning(
                t["warning"], 
                msg + "\n\n" + t["check_process"]))
        elif spc_varovani:
            # ORANŽOVÝ POPLACH (SPC Varování) - jen info, díl je fyzicky OK
            try: self.bell() 
            except: pass
            self.after(300, lambda: messagebox.showinfo(
                t["spc_warning"],
                msg + "\n\n" + t["check_process"]))
            
        status = "OK" if self.lsl <= value <= self.usl else "NOK"
        teor_ted = datetime.datetime.now()
        datum = teor_ted.strftime("%Y-%m-%d")
        plny_cas = teor_ted.strftime("%H:%M:%S") 

        new_row = {"Datum": datum, "Cas": plny_cas, "Hodnota": value, "Operator": operator,"Smena": smena, "Status": status}
        self.df = pd.concat([self.df, pd.DataFrame([new_row])], ignore_index=True)
        
        self.ulozit_do_csv(datum, plny_cas, value, operator, smena, status)
        self.timer_seconds = self.shift_duration

        pocet_dat = len(self.df)

        if pocet_dat == self.LIMIT_PRO_UCL_FIX and self.fixed_ucl is None:
            print(f"Dosaženo {self.LIMIT_PRO_UCL_FIX} měření. Fixuji UCL/LCL...")
            
            mean = self.df["Hodnota"].mean()
            std = self.df["Hodnota"].std()
            
            if std > 0:
                # 1. Vypočítáme limity
                nove_ucl = mean + (3 * std)
                nove_lcl = mean - (3 * std)
                
                # Zaokrouhlíme na 3 desetinná místa pro hezký zápis
                nove_ucl = round(nove_ucl, 3)
                nove_lcl = round(nove_lcl, 3)

                # 2. Uložíme do paměti aplikace (okamžitá změna v grafu)
                self.fixed_ucl = nove_ucl
                self.fixed_lcl = nove_lcl
                
                # 3. Zapíšeme NAVŽDY do souboru CSV (modely_spc.csv)
                # Musíme tam poslat i všechny ostatní parametry, aby se nesmazaly
                self.aktualizovat_databazi_modelu(
                    self.aktualni_model,
                    self.current_set_line,
                    self.usl,
                    self.lsl,
                    self.target,
                    int(self.shift_duration / 60), # Timer v minutách
                    str(nove_ucl), # UCL
                    str(nove_lcl)  # LCL
                )
                
                def zobrazit_info_okno():
                    messagebox.showinfo(
                        "SPC Info", 
                        f"Proces byl stabilizován.\n\nUCL a LCL byly automaticky vypočteny a zafixovány:\nUCL: {nove_ucl}\nLCL: {nove_lcl}"
                    )
                self.after(300, zobrazit_info_okno)

        try:
            self.lbl_timer_val.configure(text_color="#3B8ED0")
        except: pass
        
        self.update_graph()
        self.aktualizovat_semafor()

    def nastaveni_app(self, vynucene_otevreni=False):
        self.okno_nastaveni = ctk.CTkToplevel(self)
        self.umistit_okno_na_obrazovce(self.okno_nastaveni, 400, 500, typ_okna="nastaveni")
        t = TEXTS[self.jazyk]
        self.okno_nastaveni.title(t["settings"])
        self.okno_nastaveni.attributes("-topmost", True)
        self.okno_nastaveni.grab_set()
        
        if vynucene_otevreni:
            def zeptat_na_zavreni():
                ukoncit = messagebox.askyesno(
                    "Quit Confirmation", 
                    "Without initial setup, the application cannot be used.\n\nDo you want to completely exit the application?",
                    parent=self.okno_nastaveni,
                    icon="warning"
                )
                if ukoncit:
                    self.destroy() 
            self.okno_nastaveni.protocol("WM_DELETE_WINDOW", zeptat_na_zavreni)

        ctk.CTkLabel(self.okno_nastaveni, text=t["settings"], font=("Arial", 24, "bold")).pack(pady=(20, 10))
        self.vykreslit_formular_nastaveni()

    def vykreslit_formular_nastaveni(self):
        t = TEXTS[self.jazyk]
        self.umistit_okno_na_obrazovce(self.okno_nastaveni, 340, 350, typ_okna="formular_nastaveni")
        
        frm = ctk.CTkFrame(self.okno_nastaveni, fg_color="transparent")
        frm.pack(pady=10, padx=20, fill="both", expand=True)

        # 1. LINKA
        curr_line = self.settings.get("line")
        self.entry_line = self._vytvorit_radek(frm, 1, t["line"], curr_line)
        
        # 2. VZHLED
        curr_appearance = self.settings.get("appearance_mode")
        self.entry_appearance = self._vytvorit_radek(frm, 2, t["appearance_mode"], curr_appearance)
        
        # 3. BARVA TÉMATU
        curr_color_theme = self.settings.get("color_theme")
        self.entry_color_theme = self._vytvorit_radek(frm, 3, t["color_theme"], curr_color_theme)
        
        # Správa operátorů

        self.operator_options = self._vytvorit_radek(frm, 4, t["manage_operators"], None) # Prázdný string protože to není input
        
        # Sekundy
        #self.switch_seconds = ctk.CTkSwitch(frm, text=t["show_seconds"])
        #self.switch_seconds.grid(row=4, column=0, columnspan=2, pady=20)
        #if self.zobrazit_sekundy: self.switch_seconds.select(), už nebudu potřebovat

        # Uložit
        ctk.CTkButton(self.okno_nastaveni, text=t["btn_save_general_setting"], command=self.ulozit_globalni_nastaveni, height=40).pack(pady=20, padx=20, fill="x")

    def ulozit_globalni_nastaveni(self):
        t = TEXTS[self.jazyk]
        new_line = self.entry_line.get()
        if new_line in ["N/A", "", t["just_choose"]]:
             messagebox.showerror(t["error"], t["choose_line"], parent=self.okno_nastaveni)
             return
        old_line = self.current_set_line
        is_first_setup = old_line in ["N/A", t["just_choose"], "", None]
        is_changing_line = new_line != old_line
        if not is_first_setup and is_changing_line:
            if not self.overit_heslo(okno=self.okno_nastaveni):
                return
            print("Změna linky detekována - resetuji graf.")
            self.aktualni_model = "N/A"          # Zapomeneme aktuální model
            self.settings.set("project", "N/A")  # Uložíme do nastavení "N/A"
            self.df = pd.DataFrame()             # Vymažeme data z paměti
            self.usl = 0
            self.lsl = 0
            self.target = 0
        #show_seconds_mode_switch = self.settings.get("show_seconds")
        #if show_seconds_mode_switch != self.switch_seconds.get():
            #if not self.overit_heslo(okno=self.okno_nastaveni):
                #return
        new_appearance = self.entry_appearance.get()
        zvoleny_vzhled_text = self.entry_appearance.get()
        new_color_theme_text = self.entry_color_theme.get()
        new_color_theme = self.entry_color_theme.get() # možná později přidat volbu barvy textu?
        mapa_barev = {"blue": t["theme_blue"], "green": t["theme_green"]}
        for k, v in mapa_barev.items():
            if v == new_color_theme_text:
                new_color_theme = k
                break
        finalni_vzhled_kod = "Dark" # Default
        for systemovy_nazev, prelozeny_nazev in self.mapa_modu.items():
            if prelozeny_nazev == zvoleny_vzhled_text:
                finalni_vzhled_kod = systemovy_nazev
                break        
        self.settings.set("line", new_line)
        self.settings.set("appearance_mode", finalni_vzhled_kod)
        self.settings.set("color_theme", new_color_theme)
        #self.settings.set("show_seconds", self.switch_seconds.get())
        
        self.current_set_line = new_line
        #self.zobrazit_sekundy = self.switch_seconds.get()
        
        # Aplikace změn HNED
        ctk.set_appearance_mode(finalni_vzhled_kod)
        ctk.set_default_color_theme(new_color_theme)
        # Barva se aplikuje až po restartu většinou, ale nastavíme ji
        
        self.okno_nastaveni.destroy()
        self.clear_ui()
        self.setup_ui()
        if not self.df.empty:
            self.update_graph()

    def _vytvorit_radek(self, parent, row, label_text, value):
        t= TEXTS[self.jazyk]
        ctk.CTkLabel(parent, text=label_text, font=("Arial", 14)).grid(row=row, column=0, sticky="w", pady=10, padx=10)
        
        if label_text == t["appearance_mode"]:
            # 1. Definice mapy (Klíč pro systém : Text pro lidi)
            self.mapa_modu = {"Light": t["mode_light"], "Dark": t["mode_dark"], "System": t["mode_system"]
            }
            
            option = ctk.CTkOptionMenu(parent, values=list(self.mapa_modu.values()), width=120, font=("Arial", 14))
            option.grid(row=row, column=1, sticky="e", pady=10, padx=10)
            aktualni_zobrazeny_text = self.mapa_modu.get(value, t["mode_dark"])
            option.set(aktualni_zobrazeny_text)
            return option
        elif label_text == t["color_theme"]:
            self.mapa_barev = {"blue": t["theme_blue"], "green": t["theme_green"]}
            option = ctk.CTkOptionMenu(parent, values=list(self.mapa_barev.values()), width=120, font=("Arial", 14))
            option.grid(row=row, column=1, sticky="e", pady=10, padx=10)
            option.set(self.mapa_barev.get(value, t["theme_blue"]))
            return option
        elif label_text == t["line"]:
            lines = ["L63", "L64", "L67", "W06", "W07", "W08", "W09"]
            option = ctk.CTkOptionMenu(parent, values=lines, width=120, font=("Arial", 14))
            option.grid(row=row, column=1, sticky="e", pady=10, padx=10)
            option.set(value if value in lines else t["just_choose"])
            return option
        elif label_text == t["manage_operators"]:
            # Vytvoříme tlačítko. 
            # 'value' zde nepoužíváme, protože tlačítko nemá hodnotu, jen akci.
            btn_ops = ctk.CTkButton(
                parent, 
                text=t["btn_edit"], # Text na tlačítku
                command=self.otevrit_spravu_operatoru,
                font=("Arial", 14),
                width=120)
            btn_ops.grid(row=row, column=1, sticky="e", pady=10, padx=10)
            return btn_ops
        

        entry = ctk.CTkEntry(parent, width=120, justify="center")
        entry.grid(row=row, column=1, sticky="e", pady=10, padx=10)
        if value is not None: entry.insert(0, str(value))
        return entry
    
    def otevrit_spravu_operatoru(self):
        """Otevře okno pro přidávání/odebírání operátorů."""
        # 1. Bezpečnostní ověření heslem (volitelné, ale doporučené)
        if not self.overit_heslo(okno=self.okno_nastaveni):
            return
        
        if not self.settings.get("line") == "N/A":
            if self.okno_nastaveni.winfo_exists():
                    self.okno_nastaveni.destroy()
                
        t = TEXTS[self.jazyk]
        
        # 2. Vytvoření okna
        self.win_ops = ctk.CTkToplevel(self)
        self.win_ops.title(t["manage_operators"])
        self.umistit_okno_na_obrazovce(self.win_ops, 400, 600)
        self.win_ops.attributes("-topmost", True)
        self.win_ops.grab_set()

        # Nadpis
        ctk.CTkLabel(self.win_ops, text=t["manage_operators"], font=("Arial", 20, "bold")).pack(pady=15)

        # 3. Sekce pro PŘIDÁNÍ nového
        frame_for_new_operator = ctk.CTkFrame(self.win_ops, fg_color="transparent")
        frame_for_new_operator.pack(fill="x", padx=20, pady=10)
        frame_for_new_operator.columnconfigure(0, weight=1)
        frame_for_new_operator.columnconfigure(1, weight=1)
        frame_for_new_operator.columnconfigure(2, weight=0)

        self.entry_new_op_number = ctk.CTkEntry(frame_for_new_operator, placeholder_text=t["add_operator_number_placeholder"], width=50)
        self.entry_new_op_number.grid(row=0, column=0, sticky="ew", padx= 5, pady=10)
        self.entry_new_op_name = ctk.CTkEntry(frame_for_new_operator, placeholder_text=t["add_operator_name_placeholder"], width=170)
        self.entry_new_op_name.grid(row=0, column=1, sticky="ew", padx= 5, pady=10)

        btn_add = ctk.CTkButton(frame_for_new_operator, text= "+", width=40, command=self._pridat_operatora)
        btn_add.grid(row=0, column=2, padx= 10, pady=10)
        
        # Bind Enter klávesy pro rychlé přidávání
        self.entry_new_op_number.bind("<Return>", lambda event: self._pridat_operatora())
        self.entry_new_op_name.bind("<Return>", lambda event: self._pridat_operatora())

        # 4. Sekce SEZNAMU (Rolovací)
        self.scroll_ops = ctk.CTkScrollableFrame(self.win_ops, label_text=t["operators_title"], fg_color="transparent")
        self.scroll_ops.pack(fill="both", expand=True, padx=20, pady=10)

        # Načtení a vykreslení seznamu
        self._aktualizovat_seznam_operatoru_gui()

    def _aktualizovat_seznam_operatoru_gui(self):
        """Smaže starý seznam v GUI a vykreslí aktuální z CSV."""
        t = TEXTS[self.jazyk]
        
        # Vyčistit scroll frame
        for widget in self.scroll_ops.winfo_children():
            widget.destroy()

        # Načíst operátory ze souboru (nebo proměnné)
        operatori = self.nacist_operatory() # Tuto metodu už asi máš, nebo viz níže

        for op in operatori:
            if op.strip() == "": continue # Přeskočit prázdné řádky
            
            row = ctk.CTkFrame(self.scroll_ops, fg_color="transparent")
            row.pack(fill="x", pady=2)
            
            # Jméno operátora
            lbl = ctk.CTkLabel(row, text=op, font=("Arial", 14), anchor="w")
            lbl.pack(side="left", padx=10)
            
            # Tlačítko smazat (používáme lambda pro předání konkrétního jména)
            btn_del = ctk.CTkButton(
                row, 
                text=t["btn_delete"], 
                width=60, 
                height=25,
                fg_color="#FF3333", 
                hover_color="#CC0000",
                command=lambda jmeno=op: self._smazat_operatora(jmeno)
            )
            btn_del.pack(side="right", padx=10)

    def _pridat_operatora(self):
        """Logika přidání operátora do CSV."""
        t = TEXTS[self.jazyk]
        nove_cislo = self.entry_new_op_number.get().strip()
        nove_jmeno = self.entry_new_op_name.get().strip()
        
        if not nove_jmeno or not nove_cislo:
            messagebox.showerror(t["error"], t["operator_number_and_name_required"], parent=self.win_ops)
            return
        
        if not nove_cislo.isdigit():
            messagebox.showerror(t["error"], t["operator_number_must_be_digit"], parent=self.win_ops)
            return
        
        jmeno_a_cislo_operator = f"{nove_cislo} - {nove_jmeno}"

        aktualni_seznam = self.nacist_operatory()
        
        if jmeno_a_cislo_operator in aktualni_seznam:
            messagebox.showwarning(t["warning"], t["operator_exists"], parent=self.win_ops)
            return

        # Zápis do CSV (append)
        try:
            with open(self.cesta_operatori, mode="a", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow([jmeno_a_cislo_operator])
            
            self.entry_new_op_number.delete(0, "end") # Vymazat entry
            self.entry_new_op_name.delete(0, "end") # Vymazat entry
            self._aktualizovat_seznam_operatoru_gui() # Obnovit seznam
            
            
        except Exception as e:
            messagebox.showerror("Error", f"Chyba zápisu: {e}", parent=self.win_ops)

    def _smazat_operatora(self, jmeno_k_smazani):
        """Logika smazání operátora z CSV."""
        t = TEXTS[self.jazyk]
        aktualni_seznam = self.nacist_operatory()
        if len(aktualni_seznam) <= 1:
            messagebox.showwarning(t["warning"], t["min_one_operator"], parent=self.win_ops)
            return
        # Potvrzení (volitelné)
        zprava_o_smazani = t["confirm_delete_operator"].format(jmeno=jmeno_k_smazani)
        if not messagebox.askyesno(t["btn_delete"], zprava_o_smazani, parent=self.win_ops):
            return

        novy_seznam = [op for op in aktualni_seznam if op != jmeno_k_smazani]

        # Přepis celého souboru
        try:
            with open(self.cesta_operatori, mode="w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, delimiter=";")
                for op in novy_seznam:
                    writer.writerow([op])
            
            self._aktualizovat_seznam_operatoru_gui()
            
        except Exception as e:
            messagebox.showerror("Error", f"Chyba mazání: {e}", parent=self.win_ops)

    # --- Pomocná metoda pro načtení (pokud ji ještě nemáš) ---
    def nacist_operatory(self):
        """Vrátí list jmen operátorů."""
        seznam = []
        if not os.path.exists(self.cesta_operatori):
            return []
            
        try:
            with open(self.cesta_operatori, mode="r", encoding="utf-8-sig") as f:
                reader = csv.reader(f, delimiter=";")
                # Pokud máš hlavičku, odkomentuj:
                # next(reader, None) 
                for row in reader:
                        seznam.append(row[0])
        except Exception:
            return []
        return seznam # Seřazeno podle abecedy
    
if __name__ == "__main__":
    app = SPCApp()
    app.mainloop()


""" co dodělat dál:
- dodělat okno měření s váhami
- upravit design správa operátorů
- přidat nový barvičky
- do budoucna přidat uplně všude angličtinu






"""
