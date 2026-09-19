/*
 * M20.4 frontend bridge helper.
 *
 * This file does not own the UI. It provides one small API surface that
 * existing frontend pages can use in later phases.
 */

window.WAYMARKBridge = {
    available() {
        return !!window.waymark && typeof window.waymark.invoke === "function";
    },

    async invoke(action, payload = {}) {
        if (!this.available()) {
            throw new Error("WAYMARK desktop bridge is not available.");
        }

        return window.waymark.invoke(action, payload);
    },

    health() {
        return this.invoke("health");
    },

    search(query) {
        return this.invoke("search", { query });
    },

    library() {
        return this.invoke("library");
    },

    history(limit = 20) {
        return this.invoke("history", { limit });
    }
};
