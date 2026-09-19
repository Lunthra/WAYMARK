const path = require("path");

module.exports = {
    packagerConfig: {
        asar: true,
        executableName: "WAYMARK",
        extraResource: [
            path.resolve(__dirname, "../frontend"),
            path.resolve(__dirname, "../backend/data"),
            path.resolve(__dirname, "../../dist/WAYMARK-backend.exe")
        ]
    },
    makers: [
        {
            name: "@electron-forge/maker-squirrel",
            config: {
                name: "waymark",
                setupExe: "WAYMARK-Setup.exe"
            }
        }
    ]
};
