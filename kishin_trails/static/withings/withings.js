// Shows the authorisation code Withings appends to this page's address after the user
// approves access (OAuth redirect: ?code=...&state=...), so that it can be copied into the
// program that asked for it. Nothing is sent anywhere: the page only reads its own address.

(function () {
  const params = new URLSearchParams(window.location.search);
  const code = params.get("code");
  const error = params.get("error");
  const message = document.getElementById("message");
  const field = document.getElementById("code");
  const copyButton = document.getElementById("copy");
  const note = document.getElementById("note");

  if (error) {
    message.textContent = "Withings returned an error: " + error;
    message.className = "error";
    return;
  }
  if (!code) {
    message.textContent = "This address has no authorisation code. Open it through the link the program prints.";
    return;
  }

  message.textContent = "Your authorisation code:";
  field.value = code;
  field.hidden = false;
  copyButton.hidden = false;
  note.hidden = false;
  field.select();

  copyButton.addEventListener("click", function () {
    navigator.clipboard.writeText(code).then(
      function () { copyButton.textContent = "Copied"; },
      function () { field.select(); copyButton.textContent = "Copy failed, select and copy by hand"; }
    );
  });
})();
