import json
import os
import re
import sqlite3
from datetime import datetime
import pandas as pd
import streamlit as st
from streamlit_ace import st_ace
from streamlit_tags import st_tags

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Prompt Vault",
    page_icon="🗂️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- DATABASE SETUP ---
DB_PATH = "prompts.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                folder TEXT DEFAULT 'General',
                tags TEXT,
                model_target TEXT,
                content TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                parent_id INTEGER DEFAULT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        columns = [row[1] for row in conn.execute("PRAGMA table_info(prompts)").fetchall()]
        if "folder" not in columns:
            conn.execute("ALTER TABLE prompts ADD COLUMN folder TEXT DEFAULT 'General'")
        if "version" not in columns:
            conn.execute("ALTER TABLE prompts ADD COLUMN version INTEGER DEFAULT 1")
        if "parent_id" not in columns:
            conn.execute("ALTER TABLE prompts ADD COLUMN parent_id INTEGER DEFAULT NULL")
        conn.commit()

def get_all_prompts():
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query("SELECT * FROM prompts ORDER BY updated_at DESC", conn)

def save_prompt(prompt_id, title, folder, tags, model_target, content, version=1, parent_id=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    folder_clean = folder.strip() if folder and folder.strip() else "General"
    tags_str = ",".join([t.strip() for t in tags if t.strip()])
    
    with sqlite3.connect(DB_PATH) as conn:
        if prompt_id is None:
            conn.execute(
                "INSERT INTO prompts (title, folder, tags, model_target, content, version, parent_id, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (title, folder_clean, tags_str, model_target, content, version, parent_id, now),
            )
        else:
            conn.execute(
                "UPDATE prompts SET title=?, folder=?, tags=?, model_target=?, content=?, version=?, updated_at=? WHERE id=?",
                (title, folder_clean, tags_str, model_target, content, version, now, prompt_id),
            )
        conn.commit()

def delete_prompt(prompt_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM prompts WHERE id=?", (prompt_id,))
        conn.commit()

def create_folder(folder_name):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO prompts (title, folder, tags, model_target, content, version, parent_id, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (f"[{folder_name} Guide]", folder_name, "folder-placeholder", "Any", "Delete this placeholder once you add prompts to this folder.", 1, None, now)
        )
        conn.commit()

def delete_folder(folder_name):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM prompts WHERE folder=?", (folder_name,))
        conn.commit()

def import_prompts_from_json(json_bytes):
    try:
        data = json.loads(json_bytes.decode("utf-8"))
        if not isinstance(data, list):
            return False, "Invalid JSON format: Expected a list of prompts."
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        with sqlite3.connect(DB_PATH) as conn:
            for item in data:
                title = item.get("title", "Untitled Prompt")
                folder = item.get("folder", "General")
                tags = item.get("tags", "")
                model_target = item.get("model_target", "Any")
                content = item.get("content", "")
                version = item.get("version", 1)
                parent_id = item.get("parent_id", None)
                updated_at = item.get("updated_at", now)
                
                conn.execute(
                    "INSERT INTO prompts (title, folder, tags, model_target, content, version, parent_id, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (title, folder, tags, model_target, content, version, parent_id, updated_at)
                )
            conn.commit()
        return True, f"Successfully imported {len(data)} prompts!"
    except Exception as e:
        return False, f"Import failed: {str(e)}"

init_db()

# --- SESSION STATE ---
if "selected_id" not in st.session_state:
    st.session_state.selected_id = None

# --- SIDEBAR: LIBRARY & SEARCH ---
with st.sidebar:
    st.title("🗂️ Prompt Vault")
    st.caption("Storage: Local SQLite Database")
    
    col_nb1, col_nb2 = st.columns(2)
    with col_nb1:
        if st.button("➕ New Prompt", use_container_width=True, type="primary"):
            st.session_state.selected_id = None
            st.rerun()
    with col_nb2:
        if st.button("📁 New Folder", use_container_width=True):
            st.session_state.show_new_folder_modal = True

    if st.session_state.get("show_new_folder_modal", False):
        with st.form("new_folder_form"):
            new_f_name = st.text_input("Folder Name")
            submitted = st.form_submit_button("Create Folder")
            if submitted and new_f_name.strip():
                create_folder(new_f_name.strip())
                st.session_state.show_new_folder_modal = False
                st.rerun()

    st.divider()
    
    with st.expander("⚙️ Backup & Sync"):
        db_modified = datetime.fromtimestamp(os.path.getmtime(DB_PATH)).strftime('%Y-%m-%d %H:%M') if os.path.exists(DB_PATH) else "Unknown"
        st.caption(f"💾 Last DB update: {db_modified}")
        st.warning("⚠️ **Cloud Storage Notice:** Streamlit Community Cloud containers reset on reboot. Remember to export JSON backups regularly!")

        df_export = get_all_prompts()
        if not df_export.empty:
            export_data = df_export[["title", "folder", "tags", "model_target", "content", "version", "parent_id", "updated_at"]].to_dict(orient="records")
            json_str = json.dumps(export_data, indent=4)
            st.download_button(
                label="📥 Export Vault (JSON)",
                data=json_str,
                file_name=f"prompt_vault_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                mime="application/json",
                use_container_width=True,
            )
        
        uploaded_file = st.file_uploader("📤 Import Vault (JSON)", type=["json"])
        if uploaded_file is not None:
            if st.button("Confirm Import", use_container_width=True):
                success, message = import_prompts_from_json(uploaded_file.getvalue())
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)

    st.divider()
    
    search_query = st.text_input("🔍 Search title, content, or tags", placeholder="e.g., python, summary")
    df = get_all_prompts()
    
    if not df.empty and search_query:
        mask = (
            df["title"].str.contains(search_query, case=False, na=False)
            | df["tags"].str.contains(search_query, case=False, na=False)
            | df["content"].str.contains(search_query, case=False, na=False)
        )
        df = df[mask]
        
    st.caption(f"Saved Prompts ({len(df)})")
    
    if not df.empty:
        df["folder"] = df["folder"].fillna("General").replace("", "General")
        
        for folder_name, group in df.groupby("folder", sort=True):
            with st.expander(f"📁 {folder_name} ({len(group)})", expanded=True):
                if folder_name != "General":
                    if st.button(f"🗑️ Delete Folder '{folder_name}'", key=f"delf_{folder_name}", use_container_width=True):
                        delete_folder(folder_name)
                        st.rerun()
                    st.markdown("---")

                for _, row in group.iterrows():
                    version_badge = f" (v{row.get('version', 1)})" if row.get('version', 1) > 1 else ""
                    label = f"**{row['title']}**{version_badge}"
                    if row["tags"]:
                        label += f"  \n`{row['tags']}`"
                    if st.button(label, key=f"nav_{row['id']}", use_container_width=True):
                        st.session_state.selected_id = int(row["id"])
                        st.rerun()

# --- LOAD ACTIVE PROMPT ---
active_prompt = None
if st.session_state.selected_id is not None:
    match = get_all_prompts()
    match = match[match["id"] == st.session_state.selected_id]
    if not match.empty:
        active_prompt = match.iloc[0]

default_title = active_prompt["title"] if active_prompt is not None else ""
default_folder = (
    active_prompt["folder"]
    if (active_prompt is not None and pd.notna(active_prompt["folder"]) and active_prompt["folder"])
    else "General"
)
default_tags = (
    [t for t in active_prompt["tags"].split(",") if t]
    if (active_prompt is not None and active_prompt["tags"])
    else []
)
default_model = active_prompt["model_target"] if active_prompt is not None else "Any"
default_content = (
    active_prompt["content"]
    if active_prompt is not None
    else "You are an expert assistant.\n\nTask: {{task}}\nContext: {{context}}"
)

# --- MAIN WORKSPACE ---
col_editor, col_runner = st.columns([1.3, 1], gap="large")

with col_editor:
    st.subheader("✏️ Edit Prompt" if active_prompt is not None else "✨ Create Prompt")
    
    all_df = get_all_prompts()
    existing_folders = sorted(
        list(set(["General"] + all_df["folder"].dropna().tolist()))
    ) if not all_df.empty and "folder" in all_df.columns else ["General"]

    f_col1, f_col2 = st.columns([2, 1])
    with f_col1:
        selected_folder = st.selectbox(
            "Folder",
            options=existing_folders + ["➕ Create new folder..."],
            index=existing_folders.index(default_folder) if default_folder in existing_folders else 0,
        )
    with f_col2:
        if selected_folder == "➕ Create new folder...":
            folder = st.text_input("New Folder Name", placeholder="e.g., Agents")
        else:
            folder = selected_folder

    c1, c2 = st.columns(2)
    with c1:
        title = st.text_input("Prompt Title", value=default_title, placeholder="e.g., Code Reviewer")
    with c2:
        models = ["Any", "Claude 3.5 / 4", "GPT-4o / o3", "Gemini 2.5", "Local / Llama"]
        model_idx = models.index(default_model) if default_model in models else 0
        model_target = st.selectbox("Target Model", models, index=model_idx)
        
    tags = st_tags(
        label="Tags",
        text="Press enter to add tag",
        value=default_tags,
        suggestions=["system", "coding", "analysis", "creative", "utility"],
        maxtags=8,
        key=f"tags_{st.session_state.selected_id}",
    )
    
    st.markdown("**Prompt Template** *(use `{{variable_name}}` for placeholders)*")
    content = st_ace(
        value=default_content,
        language="markdown",
        theme="tomorrow_night",
        height=340,
        wrap=True,
        show_gutter=True,
        auto_update=True,
        key=f"ace_{st.session_state.selected_id}",
    )
    
    char_count = len(content)
    word_count = len(content.split())
    est_tokens = max(1, round(char_count / 4))
    st.caption(f"📊 **Stats:** {char_count} characters | ~{word_count} words | **~{est_tokens} tokens** (estimated)")

    btn_save, btn_dup, btn_del = st.columns(3)
    with btn_save:
        if st.button("💾 Save", type="primary", use_container_width=True):
            if not title.strip():
                st.error("Please enter a title.")
            else:
                current_version = int(active_prompt["version"]) if active_prompt is not None and "version" in active_prompt else 1
                current_parent = int(active_prompt["parent_id"]) if active_prompt is not None and pd.notna(active_prompt.get("parent_id")) else None
                save_prompt(st.session_state.selected_id, title.strip(), folder, tags, model_target, content, version=current_version, parent_id=current_parent)
                st.success("Saved!")
                st.rerun()
                
    with btn_dup:
        if active_prompt is not None:
            if st.button("📋 Duplicate (New Version)", use_container_width=True):
                next_version = int(active_prompt.get("version", 1)) + 1
                parent = int(active_prompt.get("parent_id") or active_prompt["id"])
                save_prompt(
                    prompt_id=None, 
                    title=f"{title.strip()} (v{next_version})", 
                    folder=folder, 
                    tags=tags, 
                    model_target=model_target, 
                    content=content, 
                    version=next_version, 
                    parent_id=parent
                )
                st.success(f"Duplicated as v{next_version}!")
                st.rerun()

    with btn_del:
        if active_prompt is not None:
            if st.button("🗑️ Delete", use_container_width=True):
                delete_prompt(st.session_state.selected_id)
                st.session_state.selected_id = None
                st.rerun()

with col_runner:
    st.subheader("🚀 Fill & Copy")
    st.caption("Detected `{{variables}}` appear below. Fill them in to compile your final prompt.")
    
    variables = list(dict.fromkeys(re.findall(r"\{\{([a-zA-Z0-9_]+)\}\}", content)))
    compiled_prompt = content
    
    if variables:
        for var in variables:
            user_val = st.text_area(
                f"`{{{{{var}}}}}`",
                height=75,
                placeholder=f"Enter value for {var}...",
                key=f"var_{st.session_state.selected_id}_{var}",
            )
            if user_val:
                compiled_prompt = compiled_prompt.replace(f"{{{{{var}}}}}", user_val)
    else:
        st.info("No `{{variables}}` detected in this prompt.")
        
    st.markdown("**Final Output** *(hover top-right corner to copy)*")
    st.code(compiled_prompt, language="markdown", wrap_lines=True)
