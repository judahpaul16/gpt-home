import React from 'react';
import '../css/About.css';

const About: React.FC = () => {

  return (
    <div className="dashboard about-dashboard">
      <h2>About</h2>
      <div className="about-container">
        ChatGPT at home! Basically a better G**gle Nest Hub desk assistant.
        <br/>
        Built on the Raspberry Pi using the OpenAI API.
        <br/><br/>
        Made with &hearts; by Judah Paul.
        <br/><br/>
        Learn more @ <a target='_blank' rel='noopener noreferrer'
                      href="https://github.com/judahpaul16/gpt-home">
                      github.com/judahpaul16/gpt-home
                    </a>
      </div>
    </div>
  );
};

export default About;
