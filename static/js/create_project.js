document.addEventListener("DOMContentLoaded", function () {

    const form = document.querySelector("form");
    const generateBtn = document.querySelector(".generate-btn");
    const saveBtn = document.querySelector(".save-btn");

    // -----------------------------
    // Generate Button Loading State
    // -----------------------------
    if (form && generateBtn) {

        form.addEventListener("submit", function () {

            generateBtn.disabled = true;
            generateBtn.innerHTML = "Generating Project...";

        });

    }

    // -----------------------------
    // Save Button
    // -----------------------------
    if (saveBtn) {

        saveBtn.addEventListener("click", function () {

            alert("Saving will be implemented in the next step.");

        });

    }

    // -----------------------------
    // Unsaved Changes Detection
    // -----------------------------
    let changed = false;

    const inputs = document.querySelectorAll("input, textarea");

    inputs.forEach(function (input) {

        input.addEventListener("input", function () {

            changed = true;

        });

    });

    window.addEventListener("beforeunload", function (e) {

        if (changed) {

            e.preventDefault();
            e.returnValue = "";

        }

    });

});