

# Connect to a Amazon DCV server and get the first frame
<a name="establish-connection"></a>

The following tutorial shows you how to prepare your HTML page for your custom web client, how to authenticate and connect to a Amazon DCV server, and how to receive the first frame of streamed content from the Amazon DCV session.

**Topics**
+ [Step 1: Prepare your HTML page](#prep-html)
+ [Step 2: Authenticate, connect, and get the first frame](#auth-conn)
+ [Bonus: Automatically create an HTML login form](#get-token)

## Step 1: Prepare your HTML page
<a name="prep-html"></a>

 In your web page, you must load the needed JavaScript modules and you must add a `<div>` HTML element with a valid `id` where you want the Amazon DCV Web Client SDK to draw the content stream from the remote Amazon DCV server. 

For example:

```
<!DOCTYPE html>
<html lang="en" style="height: 100%;">
  <head>
    <title>DCV first connection</title>
  </head>
  <body style="height: 100%;">
    <div id="root" style="height: 100%;"></div>
    <div id="dcv-display"></div>
    <script type="module" src="index.js"></script>
  </body>
</html>
```

## Step 2: Authenticate, connect, and get the first frame
<a name="auth-conn"></a>

This section shows how to complete the user authentication process, how to connect the Amazon DCV server, and how to receive the first frame of content from the Amazon DCV server.

 First, from the `index.js` file import the Amazon DCV Web Client SDK. It can be imported either as a Universal Module Definition (UMD) module, like so: 

```
import "./dcvjs/dcv.js"
```

 Otherwise, starting from version `1.1.0`, it can also be imported as a ECMAScript Module (ESM) from the corresponding package, like so: 

```
import dcv from "./dcvjs/dcv.js"
```

Define the variables to use to store the Authentication object, Connection object, and the Amazon DCV server URL.

```
let auth,
    connection,
    serverUrl;
```

 On script load, log the Amazon DCV Web Client SDK version, and on page load, call the `main` function. 

```
console.log("Using Amazon DCV Web Client SDK version " + dcv.version.versionStr);
document.addEventListener('DOMContentLoaded', main);
```

 The `main` function sets the log level and starts the authentication process. 

```
function main () {
  console.log("Setting log level to INFO");
  dcv.setLogLevel(dcv.LogLevel.INFO);

  serverUrl = "https://your-dcv-server-url:port/";

  console.log("Starting authentication with", serverUrl);

  auth = dcv.authenticate(
    serverUrl,
    {
      promptCredentials: onPromptCredentials,
      error: onError,
      success: onSuccess
    }
  );
}
```

 The `promptCredentials` , `error` , and `success` functions are mandatory callback functions that must be defined in the authentication process. 

 If the Amazon DCV server prompts for credentials, the `promptCredentials` callback function receives the requested credential challenge from the Amazon DCV server. If the Amazon DCV server is configured to use system authentication, then the sign-in credentials must be provided. The following code samples assume that the username is `my_dcv_user` and that the password is `my_password`. 

 If authentication fails, the `error` callback function receives an error object from the Amazon DCV server. 

 If the authentication succeeds, the `success` callback function receives an array of couples that includes the session id ( `sessionId` ) and authorization tokens ( `authToken` ) for each session that the `my_dcv_user` user is allowed to connect to on the Amazon DCV server. The following code sample calls the connect function and connects to the first session returned in the array. 

**Note**  
In the following code example, replace `MY_DCV_USER` with your own username and `MY_PASSWORD` with your own password.

```
function onPromptCredentials(auth, challenge) {
  // Let's check if in challege we have a username and password request
  if (challengeHasField(challenge, "username") && challengeHasField(challenge, "password")) {
    auth.sendCredentials({username: MY_DCV_USER, password: MY_PASSWORD})
  } else {
    // Challenge is requesting something else...
  }
}

function challengeHasField(challenge, field) {
  return challenge.requiredCredentials.some(credential => credential.name === field);
}

function onError(auth, error) {
  console.log("Error during the authentication: " + error.message);
}

// We connect to the first session returned
function onSuccess(auth, result) {
  let {sessionId, authToken} = {...result[0]};

  connect(sessionId, authToken);
}
```

 Connect to the Amazon DCV server. The `firstFrame` callback method is called when the first frame is received from the Amazon DCV server. 

```
function connect (sessionId, authToken) {
  console.log(sessionId, authToken);

  dcv.connect({
    url: serverUrl,
    sessionId: sessionId,
    authToken: authToken,
    divId: "dcv-display",
    callbacks: {
      firstFrame: () => console.log("First frame received")
    }
  }).then(function (conn) {
    console.log("Connection established!");
    connection= conn;
  }).catch(function (error) {
    console.log("Connection failed with error " + error.message);
  });
}
```

## Bonus: Automatically create an HTML login form
<a name="get-token"></a>

 The `challenge` object is returned when the `promptCredentials` callback function is called. It includes a property named `requiredCredentials` that is an array of objects - one object per credential that is requested by the Amazon DCV server. Each object includes the name and the type of the requested credential. You can use the `challenge` and `requiredCredentials` objects to automatically create an HTML login form. 

The following code sample shows you how to do this.

```
let form,
    fieldSet;

function submitCredentials (e) {
  var credentials = {};
  fieldSet.childNodes.forEach(input => credentials[input.id] = input.value);
  auth.sendCredentials(credentials);
  e.preventDefault();
}

function createLoginForm () {
  var submitButton = document.createElement("button");

  submitButton.type = "submit";
  submitButton.textContent = "Login";

  form = document.createElement("form");
  fieldSet = document.createElement("fieldset");

  form.onsubmit = submitCredentials;
  form.appendChild(fieldSet);
  form.appendChild(submitButton);

  document.body.appendChild(form);
}

function addInput (name) {
  var type = name === "password" ? "password" : "text";

  var inputField = document.createElement("input");
  inputField.name = name;
  inputField.id = name;
  inputField.placeholder = name;
  inputField.type = type;
  fieldSet.appendChild(inputField);
}

function onPromptCredentials (_, credentialsChallenge) {
  createLoginForm();
  credentialsChallenge.requiredCredentials.forEach(challenge => addInput(challenge.name));
}
```